"""① Supervisor 계획 / ④ 검토·재계획.

원칙: 판단은 LLM이, 검증은 코드가. LLM이 낸 계획을 그대로 믿지 않고
- 질문에 실제로 있는 출생연도·나이를 정규식으로 다시 확인하고(없는 값을 지어내면 버림),
- 지역은 MCP resolve_region 으로 실제로 알아들을 수 있는지 확인하고,
- 분야·문서명은 정해진 목록 밖이면 버리고,
- LLM이 모양을 아예 못 지키면 규칙만으로 계획을 만든다(fallback).
"""
import json
import re

from .mcp_tools import McpError
from .state import DOC_PROGRAMS, MAX_REPLAN, AgentState, Plan

AGENT_ROUTES = ("policy", "doc", "both")
POLICY_WORDS = ("정책", "지원", "신청", "월세", "전세", "주거", "주택", "취업", "일자리", "창업", "대출",
                "수당", "장려금", "내일배움", "카드", "저축", "계좌", "적금", "자격", "혜택", "학자금",
                "교육", "훈련", "면접", "인턴", "청년")
GREETINGS = ("안녕", "누구", "뭐 할 수", "뭘 할 수", "무엇을 할 수", "하이", "고마워", "감사")
GENERIC = ("정책", "지원", "혜택", "청년", "자격", "신청")      # 이것만으로는 무엇을 찾을지 알 수 없는 낱말
SPECIFIC = tuple(w for w in POLICY_WORDS if w not in GENERIC)
PERSONAL = ("받을 수 있", "해당", "자격이 돼", "자격 돼", "나 ", "내가", "저 ", "제가", "나한테", "저한테")
KEYWORD_HINTS = ("월세", "전세", "취업", "창업", "학자금", "내일배움", "저축", "면접", "인턴", "주거", "대출", "교육")
CONTENT_WORDS = ("뭘", "무엇", "뭐가", "어떻게", "기준", "조건", "서류", "얼마", "금액", "자격", "방법", "배울")
DOC_TOPICS = ("내일배움", "청년월세", "월세 지원", "내일저축", "저축계좌", "K-디지털", "국민취업")
PROGRAM_HINTS = {"월세": "청년월세", "내일저축": "청년내일저축계좌", "저축계좌": "청년내일저축계좌"}


# ───────────── 질문에서 직접 뽑기 (정규식) ─────────────

def extract_birth(question: str, this_year: int = 2026) -> dict:
    """'2002년생', '02년생', '2002년 5월 3일생' → {"year":..,"month":..,"day":..}. 없으면 {}."""
    m = re.search(r"((?:19|20)\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*생", question)
    if m:
        return {"year": int(m[1]), "month": int(m[2]), "day": int(m[3])}
    m = re.search(r"((?:19|20)\d{2})\s*년?\s*생", question)
    if m:
        return {"year": int(m[1])}
    m = re.search(r"(?<!\d)(\d{2})\s*년\s*생", question)
    if m:
        yy = int(m[1])
        return {"year": 2000 + yy if yy <= this_year % 100 else 1900 + yy}
    return {}


def extract_age(question: str) -> int | None:
    """'24살', '만 25세' → 숫자. '20대'는 나이가 아니라 제외."""
    m = re.search(r"(?:만\s*)?(?<!\d)(\d{1,2})\s*(?:살|세)(?!대)", question)
    if m and 10 <= int(m[1]) <= 70:
        return int(m[1])
    return None


def has_any(text: str, words) -> bool:
    return any(w in text for w in words)


# ───────────── 계획 보정 ─────────────

def normalize_plan(plan: Plan, question: str, categories: list[str]) -> tuple[Plan, list[str]]:
    """LLM 계획을 질문과 대조해 고친다. 무엇을 고쳤는지 notes로 돌려준다(LangSmith·디버깅용)."""
    notes = []
    p = plan.model_copy()

    # 출생연도·나이: 질문에 있는 값이 정답. 질문에 없는데 LLM이 낸 값은 지어낸 것으로 보고 버린다.
    birth, age = extract_birth(question), extract_age(question)
    if birth:
        if p.birth_year != birth["year"]:
            notes.append(f"출생연도 보정: {p.birth_year} → {birth['year']}")
        p.birth_year, p.birth_month, p.birth_day = birth["year"], birth.get("month"), birth.get("day")
    elif p.birth_year is not None:
        notes.append(f"질문에 없는 출생연도 {p.birth_year} 제거")
        p.birth_year = p.birth_month = p.birth_day = None
    if age is not None:
        p.age = age
    elif p.age is not None:
        notes.append(f"질문에 없는 나이 {p.age} 제거")
        p.age = None
    if p.birth_year is not None and not 1950 <= p.birth_year <= 2015:
        notes.append(f"범위 밖 출생연도 {p.birth_year} 제거")
        p.birth_year = p.birth_month = p.birth_day = None
    if p.birth_month is not None and not 1 <= p.birth_month <= 12:
        p.birth_month = p.birth_day = None
    if p.birth_day is not None and not 1 <= p.birth_day <= 31:
        p.birth_day = None

    # 분야·문서명: 정해진 목록 밖이면 버린다
    if p.category and p.category not in categories:
        notes.append(f"목록에 없는 분야 '{p.category}' 제거")
        p.category = None
    if p.doc_program and p.doc_program not in DOC_PROGRAMS:
        notes.append(f"목록에 없는 문서 '{p.doc_program}' 제거")
        p.doc_program = None
    if p.keyword is not None and not p.keyword.strip():
        p.keyword = None
    if p.keyword is None:
        found = next((w for w in KEYWORD_HINTS if w in question), None)
        if found:
            notes.append(f"질문에서 키워드 '{found}' 보충")
            p.keyword = found

    # 경로 보정
    has_personal_info = p.birth_year is not None or p.age is not None or bool(p.region)
    # 인사가 섞여 있어도("안녕, 2002년생인데 월세 지원 있어?") 구체적인 정책 낱말이나 개인 정보가 있으면 정책 질문
    if p.route == "chat" and (has_any(question, SPECIFIC) or has_personal_info
                              or (has_any(question, POLICY_WORDS) and not has_any(question, GREETINGS))):
        notes.append("정책 관련 낱말이 있어 chat → both 로 보정")
        p.route = "both"
    if p.route == "clarify" and has_personal_info:
        notes.append("나이·지역 정보가 있어 clarify → both 로 보정")
        p.route = "both"
    if (p.route in ("policy", "both") and not has_personal_info and not p.keyword and not p.category
            and has_any(question, PERSONAL)):
        notes.append("개인 자격을 묻는데 정보가 없어 clarify 로 보정")
        p.route = "clarify"
    # 제도 내용(무엇을·기준·서류…)을 묻거나 안내 자료에 있는 제도 이름이 나오면 문서검색이 필요하다
    # (실측: "국민내일배움카드로 뭘 배울 수 있어?"를 qwen3가 policy로만 보냄)
    if p.route == "policy" and (has_any(question, DOC_TOPICS) or
                                (has_any(question, CONTENT_WORDS) and not has_personal_info)):
        notes.append("제도 내용을 묻는 질문이라 policy → both 로 보정")
        p.route = "both"
    if p.route in ("doc", "both") and not (p.doc_query or "").strip():
        p.doc_query = question
    return p, notes


def fallback_plan(question: str) -> Plan:
    """LLM이 계획 모양을 못 지켰을 때 규칙만으로 만드는 계획."""
    birth, age = extract_birth(question), extract_age(question)
    if has_any(question, GREETINGS) and not has_any(question, POLICY_WORDS):
        route = "chat"
    elif not (birth or age) and has_any(question, PERSONAL) and not has_any(question, SPECIFIC):
        route = "clarify"
    else:
        route = "both"
    keyword = next((w for w in KEYWORD_HINTS if w in question), None)
    program = next((v for k, v in PROGRAM_HINTS.items() if k in question), None)
    return Plan(route=route, birth_year=birth.get("year"), birth_month=birth.get("month"),
                birth_day=birth.get("day"), age=age, region=None, keyword=keyword,
                doc_query=question, doc_program=program, reason="LLM 계획 실패 → 규칙 기반 계획")


# ───────────── 노드 ─────────────

PLAN_SYSTEM = """너는 청년정책 안내 서비스의 Supervisor다. 사용자의 질문을 분석해서 계획을 JSON으로 세운다.
질문에 없는 정보(출생연도, 나이, 지역)는 절대 지어내지 말고 null로 둔다.

[route 고르는 법]
- chat: 인사, 서비스 소개 요청, 청년정책과 무관한 질문
- clarify: "나 받을 수 있는 거 있어?"처럼 개인 자격을 묻는데 나이·지역·관심 분야가 전혀 없을 때
- policy: 조건(나이·지역·분야)에 맞는 정책 목록이 필요할 때
- doc: 특정 제도의 자격 기준, 금액, 제출 서류, 예외 규정 같은 세부 설명이 필요할 때
- both: 정책 목록과 세부 설명이 둘 다 필요할 때 (예: "2002년생 전주 사는데 월세 지원 받을 수 있어?")

[분야 목록] (category는 이 중 하나만)
{categories}

[문서] (doc_program은 이 중 하나만, 해당 문서에 있을 내용이면 지정)
- 청년정책집: 고용노동부 청년 정책 종합 안내서 (취업 지원, 국민내일배움카드, K-디지털, 노동 상식 등)
- 청년월세: 전주시 청년월세 지원사업 모집공고 (자격요건, 소득·재산 기준, 제출서류, 지원금액)
- 청년내일저축계좌: 보건복지부 청년내일저축계좌 안내 (대상, 정부 지원금, 신청)
"""

REPLAN_SYSTEM = """너는 청년정책 안내 서비스의 Supervisor다. 처음 계획대로 조사했지만 결과가 부족했다.
무엇이 부족했는지 보고, 다르게 찾을 수 있도록 계획을 고쳐라 (다른 keyword·category, 더 구체적인 doc_query,
doc_program 바꾸거나 null로). 질문에 없는 정보는 지어내지 말 것. route는 policy, doc, both 중 하나.
""" + PLAN_SYSTEM.split("\n", 2)[2]


async def _llm_plan(deps, system: str, human: str) -> Plan | None:
    try:
        return await deps.llm.with_structured_output(Plan).ainvoke([("system", system), ("human", human)])
    except Exception:          # 모양을 못 지킴, 연결 실패 등 → 호출한 쪽에서 fallback
        return None


async def _resolve_region(deps, text: str | None) -> dict | None:
    if not text:
        return None
    try:
        r = await deps.mcp.call_tool("resolve_region", {"text": text})
    except McpError:
        return None
    return r if r.get("인식") else None


async def plan_node(state: AgentState, deps) -> dict:
    question = state["question"]
    catalog = await deps.mcp.read_catalog()                     # MCP Resource
    categories = catalog["분야_목록"]
    raw = await _llm_plan(deps, PLAN_SYSTEM.format(categories=", ".join(categories)), question)
    source = "llm" if raw is not None else "fallback"
    plan, notes = normalize_plan(raw or fallback_plan(question), question, categories)

    # 지역: LLM이 말한 지역이 실제로 인식되는지 확인하고, 없으면 질문 전체에서 찾는다.
    region = await _resolve_region(deps, plan.region)
    if plan.region and region is None:
        notes.append(f"지역 '{plan.region}'을 인식하지 못함")
    if region is None:   # LLM이 지역을 비웠거나 못 알아들으면 질문 글에서 직접 찾는다 (실측: qwen3가 자주 비움)
        found = await _resolve_region(deps, question)
        if found and "(" not in found["지역"]:   # '이천원' 같은 우연한 일치는 받지 않는다
            region = {**found, "입력": found["지역"]}
    plan.region = region["입력"] if region else None
    if plan.route == "clarify" and region:
        plan.route = "both"
        notes.append("지역 정보가 있어 clarify → both 로 보정")
    return {"plan": plan.model_dump(), "plan_source": source, "region_info": region,
            "replan_count": 0, "path": ["supervisor"], "llm_calls": 1,
            "notes": ([f"계획: {source}"] + notes)}


def after_plan(state: AgentState):
    route = state["plan"]["route"]
    if route == "chat":
        return "chat"
    if route == "clarify":
        return "clarify"
    return {"policy": ["policy_agent"], "doc": ["doc_agent"], "both": ["policy_agent", "doc_agent"]}[route]


def _failures(state: AgentState) -> dict:
    route = state["plan"]["route"]
    pr, dr = state.get("policy_result"), state.get("doc_result")
    fail = {}
    if route in ("policy", "both") and not (pr and pr.get("총개수", 0) > 0):
        fail["policy_agent"] = "조건에 맞는 신청 가능한 정책이 0개" if pr else "정책 조회 실패"
    if route in ("doc", "both") and not (dr and dr.get("enough")):
        fail["doc_agent"] = f"문서 조각이 답하기에 부족함({dr.get('reason') if dr else '검색 실패'})"
    return fail


async def review_node(state: AgentState, deps) -> dict:
    fail = _failures(state)
    count = state.get("replan_count", 0)
    if state["plan"]["route"] == "both" and set(fail) == {"doc_agent"}:
        # 정책 목록은 찾았고 문서 설명만 부족 → 문서는 보조 자료라 다시 찾지 않고 있는 것으로 답한다
        # (실측: 이 경우까지 재계획하면 LLM 9회·115초가 걸렸고 답은 거의 같았다)
        return {"next_agents": [], "path": ["review:정책충분"],
                "notes": ["정책은 찾음, 문서는 부족하지만 보조 자료라 재계획 생략"]}
    if not fail:
        return {"next_agents": [], "path": ["review:충분"]}
    if count >= MAX_REPLAN:
        return {"next_agents": [], "path": ["review:한도도달"],
                "notes": [f"재계획 한도({MAX_REPLAN}회) 도달: " + "; ".join(fail.values())]}
    old = Plan(**state["plan"])
    catalog = await deps.mcp.read_catalog()
    categories = catalog["분야_목록"]
    human = (f"[질문]\n{state['question']}\n\n[처음 계획]\n{json.dumps(state['plan'], ensure_ascii=False)}\n\n"
             f"[부족했던 점]\n" + "\n".join(f"- {v}" for v in fail.values()))
    raw = await _llm_plan(deps, REPLAN_SYSTEM.format(categories=", ".join(categories)), human)
    if raw is None:   # 재계획 실패 → 문서는 필터를 풀고 질문 그대로, 정책은 키워드를 빼고 다시
        raw = old.model_copy(update={"keyword": None, "category": None,
                                     "doc_query": state["question"], "doc_program": None})
    new, notes = normalize_plan(raw, state["question"], categories)
    if new.route not in AGENT_ROUTES:
        new.route = old.route
    new.region = old.region                      # 지역은 처음 확인한 값을 유지 (재계획에서 바뀌지 않게)
    covers = {"policy": {"policy_agent"}, "doc": {"doc_agent"}, "both": {"policy_agent", "doc_agent"}}
    if not set(fail) <= covers[new.route]:       # 새 계획이 실패한 쪽을 다시 안 돌리면 원래 경로 유지
        new.route = old.route
    rerun = [a for a in ("policy_agent", "doc_agent") if a in fail]
    return {"plan": new.model_dump(), "replan_count": count + 1, "next_agents": rerun,
            "path": ["review:재계획"], "llm_calls": 1,
            "notes": [f"재계획 {count + 1}회: " + "; ".join(fail.values())] + notes}


def after_review(state: AgentState):
    return state.get("next_agents") or "write"
