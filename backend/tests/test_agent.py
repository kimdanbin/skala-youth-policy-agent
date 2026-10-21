"""에이전트 그래프 테스트 — 가짜 LLM·가짜 검색기로 Ollama·벡터 DB 없이 흐름을 검사한다.

MCP는 실제 판단 함수(mcp_server/tools.py)를 그대로 부르는 가짜 연결(FakeMCP)을 쓴다:
도구 인자·결과 모양이 실제와 같아야 테스트가 의미 있기 때문이다.
진짜 MCP 서버(별도 프로세스)를 띄우는 연결 테스트는 맨 아래 test_real_mcp_server 에서 따로 한다.
"""
import asyncio
import json
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

import tools                                              # mcp_server/tools.py
from agent.deps import Deps
from agent.graph import ERROR_MESSAGE, build_graph, run
from agent.state import MAX_DOC_RETRY, MAX_DOC_RETRY_BOTH, MAX_REPLAN, Grade, Plan
from agent.supervisor import extract_age, extract_birth, fallback_plan, normalize_plan


# ───────────── 가짜 부품 ─────────────

class FakeLLM:
    """모양별로 정해 둔 답을 차례로 돌려준다. 마지막 답은 계속 반복. Exception을 넣으면 그걸 던진다."""
    def __init__(self, plans=(), grades=(), answer="테스트 답변"):
        self.queues = {"Plan": list(plans), "Grade": list(grades)}
        self.answer, self.calls = answer, []

    def with_structured_output(self, schema):
        llm = self

        class Runner:
            async def ainvoke(self, messages):
                llm.calls.append(schema.__name__)
                q = llm.queues[schema.__name__]
                item = q.pop(0) if len(q) > 1 else q[0]
                if isinstance(item, Exception):
                    raise item
                return item
        return Runner()

    async def ainvoke(self, prompt):
        self.calls.append("write")
        self.last_prompt = prompt
        return SimpleNamespace(content="<think>생각</think>" + self.answer)


class FakeMCP:
    """진짜 MCP 서버와 같은 함수(tools.py)를 부르되, 결과를 JSON으로 한 번 왕복시켜 모양을 맞춘다."""
    def __init__(self, fail_catalog=False):
        self.fail_catalog, self.calls = fail_catalog, []

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        if name == "get_today":
            return tools.get_today().isoformat()
        if name == "calc_age":
            r = tools.calc_age(**args)
        elif name == "resolve_region":
            loc = tools.resolve_region(args["text"])
            r = ({"인식": False, "입력": args["text"]} if loc is None else
                 {"인식": True, "입력": args["text"], "지역": loc["지역"], "단위": loc["단위"],
                  "코드수": len(loc["codes"])})
        elif name == "find_policies":
            r = tools.find_policies(**args)
        else:
            raise KeyError(name)
        return json.loads(json.dumps(r, ensure_ascii=False))

    async def read_catalog(self):
        if self.fail_catalog:
            raise ConnectionError("MCP 서버 연결 끊김")
        return tools.catalog()

    async def get_answer_prompt(self, question, facts):
        return f"[규칙]\n[질문]\n{question}\n[수집한 사실]\n{facts}"


class FakeSearch:
    def __init__(self):
        self.calls = []

    def __call__(self, query, k, program):
        self.calls.append((query, program))
        prog = program or "청년월세"
        return [(Document(page_content=f"{prog} 내용 {i}", metadata={"source": f"2026_{prog}_x", "program": prog,
                                                                    "page": i + 1}), 0.5 + i / 10)
                for i in range(k)]


def make(plans, grades=(Grade(enough=True, reason="ok"),), **mcp_kw):
    llm, mcp, search = FakeLLM(plans, grades), FakeMCP(**mcp_kw), FakeSearch()
    return build_graph(Deps(llm=llm, mcp=mcp, search=search)), llm, mcp, search


def ask(graph, q):
    return asyncio.run(run(graph, q))


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setenv("FAKE_TODAY", "2026-10-21")


# ───────────── 경로 ─────────────

def test_chat_route():
    g, llm, *_ = make([Plan(route="chat")])
    r = ask(g, "안녕, 넌 뭐 할 수 있어?")
    assert r["path"] == ["supervisor", "chat"] and r["llm_calls"] == 1 and "청년정책 안내" in r["answer"]


def test_clarify_route():
    g, *_ = make([Plan(route="clarify")])
    r = ask(g, "나 받을 수 있는 거 있어?")
    assert r["path"] == ["supervisor", "clarify"] and "출생 연도" in r["answer"]


def test_both_runs_two_agents_in_parallel_then_review_once():
    plan = Plan(route="both", birth_year=2002, region="전북 전주", keyword="취업", doc_query="취업 지원")
    g, llm, mcp, search = make([plan])
    r = ask(g, "2002년생 전주 사는데 취업 지원 받을 수 있어?")
    assert r["error"] is None
    assert set(r["path"][1:3]) == {"policy_agent", "doc_agent"}           # 같은 단계에서 둘 다
    assert r["path"].count("review:충분") == 1 and r["path"][-1] == "write"  # 검토는 한 번만
    assert r["llm_calls"] == 3                                            # 계획 1 + 채점 1 + 답변 1
    assert r["age"]["min"] == 23 and r["age"]["max"] == 24
    assert r["region"]["지역"] == "전북특별자치도 전주시"
    assert r["policy_total"] > 0 and r["answer"] == "테스트 답변"           # <think> 제거됨
    assert "전북특별자치도 전주시" in llm.last_prompt                       # 사실에 지역이 들어감


def test_doc_retry_and_replan_are_capped():
    """채점이 계속 '부족'이어도 재검색 MAX_DOC_RETRY회, 재계획 MAX_REPLAN회에서 멈춘다."""
    bad = Grade(enough=False, reason="기준표 없음", better_query="청년월세 자격요건 기준표")
    g, llm, mcp, search = make([Plan(route="doc", doc_query="월세 소득 기준")], grades=[bad])
    r = ask(g, "청년월세 받으려면 소득 기준이 어떻게 돼?")
    runs = MAX_REPLAN + 1
    assert len(search.calls) == runs * (MAX_DOC_RETRY + 1)
    assert r["path"].count("doc_agent") == runs and "review:한도도달" in r["path"]
    assert r["path"][-1] == "write" and r["doc_enough"] is False
    assert r["llm_calls"] == 1 + runs * (MAX_DOC_RETRY + 1) + MAX_REPLAN + 1   # 계획+채점+재계획+답변
    assert search.calls[0][1] is None and search.calls[1][1] == "청년월세"      # 2번째엔 '월세' 문서로 좁힘
    assert search.calls[1][0] == "청년월세 자격요건 기준표"                     # 채점자가 준 검색어 사용


class PickyMCP(FakeMCP):
    """정해진 키워드로만 정책이 나오는 MCP (정책조회 실패 → 재계획 상황을 만들기 위함)."""
    async def call_tool(self, name, args):
        if name != "find_policies":
            return await super().call_tool(name, args)
        self.calls.append((name, args))
        if args.get("keyword") != "되는키워드":
            return {"조건": {}, "총개수": 0, "정책": []}
        fake = {"정책명": "테스트 정책", "지역": "전국", "주관기관": "테스트", "분야": "취업", "신청상태": "신청중",
                "신청기간": "20261001 ~ 20261231", "대상연령": "19~39세", "지원내용": "", "신청방법": "", "신청주소": ""}
        return {"조건": {}, "총개수": 1, "정책": [fake]}


def test_replan_reruns_only_failed_agent():
    first = Plan(route="both", birth_year=2002, keyword="안되는키워드", doc_query="취업 지원")
    second = Plan(route="both", birth_year=2002, keyword="되는키워드", doc_query="취업 지원")
    llm, mcp, search = FakeLLM([first, second], [Grade(enough=True, reason="ok")]), PickyMCP(), FakeSearch()
    g = build_graph(Deps(llm=llm, mcp=mcp, search=search))
    r = ask(g, "2002년생인데 취업 지원 받을 수 있어?")
    assert r["path"].count("doc_agent") == 1                         # 문서는 성공했으니 다시 안 돌림
    assert r["path"].count("policy_agent") == 2 and "review:재계획" in r["path"]
    assert r["path"][-1] == "write"


def test_both_with_policy_ok_does_not_replan_for_doc():
    """정책은 찾았고 문서만 부족하면 재계획하지 않는다 (실측: 재계획하면 LLM 9회·115초)."""
    bad = Grade(enough=False, reason="없음", better_query="다른 검색어")
    g, *_ = make([Plan(route="both", birth_year=2002, keyword="취업")], grades=[bad])
    r = ask(g, "2002년생 서울 사는데 취업 지원 받을 수 있어?")
    assert "review:정책충분" in r["path"] and r["path"].count("doc_agent") == 1
    assert r["llm_calls"] == 1 + (MAX_DOC_RETRY_BOTH + 1) + 1           # both에서는 문서 재검색을 덜 한다


def test_keyword_filled_from_question_when_llm_leaves_it_empty():
    cats = tools.catalog()["분야_목록"]
    p, notes = normalize_plan(Plan(route="both", keyword=None, category="전월세 및 주거급여 지원"),
                              "2002년생 전주 사는데 월세 지원 받을 수 있어?", cats)
    assert p.keyword == "월세" and any("키워드" in n for n in notes)


def test_region_taken_from_question_when_llm_leaves_it_empty():
    """실측: qwen3가 '서울 사는데'를 보고도 region을 비웠다 → 질문 글에서 직접 찾는다."""
    g, *_ = make([Plan(route="policy", birth_year=2002, keyword="취업", region=None)])
    r = ask(g, "2002년생 서울 사는데 취업 지원 있어?")
    assert r["region"]["지역"] == "서울특별시"


def test_policy_tries_keyword_before_no_keyword():
    """실측: keyword가 비면 첫 조회가 '키워드 없이' 나가 1,078개 전체가 나왔다 → 키워드 없는 조회는 마지막."""
    g, llm, mcp, _ = make([Plan(route="policy", age=24, keyword=None, category="취업")])
    ask(g, "24살 취업 지원 있어?")
    kws = [a["keyword"] for n, a in mcp.calls if n == "find_policies"]
    assert kws[0] == "취업"


def test_content_question_gets_doc_route():
    cats = tools.catalog()["분야_목록"]
    p, _ = normalize_plan(Plan(route="policy", category="온라인교육"), "국민내일배움카드로 뭘 배울 수 있어?", cats)
    assert p.route == "both" and p.doc_query


def test_policy_broadens_when_zero():
    plan = Plan(route="policy", age=24, region="서울", keyword="절대없는낱말", category="취업")
    g, llm, mcp, _ = make([plan])
    r = ask(g, "24살 서울 사는데 지원 있어?")
    kws = [a["keyword"] for n, a in mcp.calls if n == "find_policies"]
    assert kws[:2] == ["절대없는낱말", "취업"] and r["policy_total"] > 0
    assert any("조건 넓힘" in n for n in r["notes"])


def test_llm_failure_falls_back_to_rules():
    g, *_ = make([ValueError("JSON 형식 오류")])
    r = ask(g, "2002년생 전주 사는데 월세 지원 받을 수 있어?")
    assert r["plan_source"] == "fallback" and r["error"] is None
    assert r["plan"]["route"] == "both" and r["plan"]["birth_year"] == 2002
    assert r["region"]["지역"] == "전북특별자치도 전주시"
    assert r["plan"]["doc_program"] == "청년월세"


def test_unrecognized_region_is_dropped_not_crash():
    g, *_ = make([Plan(route="policy", age=24, region="없는동네", keyword="취업")])
    r = ask(g, "24살 없는동네 사는데 취업 지원 있어?")
    assert r["error"] is None and r["region"] is None and r["policy_total"] > 0
    assert any("인식하지 못함" in n for n in r["notes"])


def test_errors_become_friendly_message():
    g, *_ = make([Plan(route="both")], fail_catalog=True)
    r = ask(g, "청년월세 기준 알려줘")
    assert r["answer"] == ERROR_MESSAGE and "ConnectionError" in r["error"]


def test_closed_policies_reported_when_none_open():
    """신청 가능한 게 0개면, 마감된 관련 정책을 따로 모아 '올해 모집은 끝났어요' 안내에 쓴다."""
    plan = Plan(route="policy", age=24, region="전주", keyword="월세")
    g, llm, *_ = make([plan])
    r = ask(g, "24살 전주 사는데 월세 지원 있어?")
    assert r["error"] is None and r["path"][-1] == "write"


# ───────────── 계획 보정 (순수 함수) ─────────────

@pytest.mark.parametrize("q, expect", [
    ("2002년생이에요", {"year": 2002}),
    ("02년생 취준생", {"year": 2002}),
    ("98년생", {"year": 1998}),
    ("2002년 5월 3일생", {"year": 2002, "month": 5, "day": 3}),
    ("2026년 신청 기간", {}),            # '생'이 없으면 출생연도가 아니다
    ("청년월세 기준", {}),
])
def test_extract_birth(q, expect):
    assert extract_birth(q) == expect


@pytest.mark.parametrize("q, expect", [("24살이야", 24), ("만 25세", 25), ("20대 청년", None), ("월세 20만원", None)])
def test_extract_age(q, expect):
    assert extract_age(q) == expect


def test_normalize_removes_hallucination_and_fixes_route():
    cats = tools.catalog()["분야_목록"]
    p, notes = normalize_plan(Plan(route="chat", birth_year=1999, category="없는분야", doc_program="없는문서"),
                              "청년월세 소득 기준이 뭐야?", cats)
    assert p.birth_year is None and p.category is None and p.doc_program is None
    assert p.route == "both" and p.doc_query == "청년월세 소득 기준이 뭐야?"
    assert len(notes) >= 3


def test_normalize_keeps_real_chat_but_fixes_mixed_greeting():
    p, _ = normalize_plan(Plan(route="chat"), "안녕, 넌 뭐 할 수 있어?", [])
    assert p.route == "chat"
    p, _ = normalize_plan(Plan(route="chat"), "안녕! 2002년생인데 월세 지원 있어?", [])
    assert p.route == "both" and p.birth_year == 2002


def test_normalize_clarify_when_personal_without_info():
    p, _ = normalize_plan(Plan(route="policy"), "나 받을 수 있는 거 있어?", [])
    assert p.route == "clarify"
    p, _ = normalize_plan(Plan(route="clarify"), "2002년생인데 받을 수 있는 거 있어?", [])
    assert p.route == "both" and p.birth_year == 2002


def test_fallback_plan_routes():
    assert fallback_plan("안녕하세요").route == "chat"
    assert fallback_plan("나 받을 수 있는 거 있어?").route == "clarify"
    assert fallback_plan("국민내일배움카드로 뭘 배울 수 있어?").route == "both"


# ───────────── 진짜 MCP 서버 연결 (별도 프로세스) ─────────────

def test_real_mcp_server():
    from agent.mcp_tools import McpError, McpTools

    async def go():
        async with McpTools() as m:
            today = await m.call_tool("get_today", {})
            age = await m.call_tool("calc_age", {"birth_year": 2002})
            reg = await m.call_tool("resolve_region", {"text": "전주"})
            pol = await m.call_tool("find_policies", {"age": 23, "age_upper": 24, "region": "전주", "limit": 3})
            cat = await m.read_catalog()
            prompt = await m.get_answer_prompt("Q", "F")
            with pytest.raises(McpError):
                await m.call_tool("find_policies", {"region": "없는지역"})
            return today, age, reg, pol, cat, prompt
    today, age, reg, pol, cat, prompt = asyncio.run(go())
    assert today == "2026-10-21"                              # FAKE_TODAY가 서버 프로세스까지 전달됨
    assert age["만나이_최소"] == 23 and reg["지역"] == "전북특별자치도 전주시"
    assert pol["조건"]["지역"] == "전북특별자치도 전주시" and len(pol["정책"]) <= 3
    assert cat["전체_정책수"] == 3472 and "6. 끝에 참고한 출처" in prompt
