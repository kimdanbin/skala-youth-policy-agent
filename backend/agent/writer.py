"""⑤ 답변 쓰기 / ⑥ 바로 답변 / ⑦ 되묻기.

답변 규칙은 MCP Prompt(policy_answer_prompt)에서 받아온다 → 규칙을 서버 한 곳에서 관리.
⑥⑦은 LLM 없이 정해진 문구: 빠르고, 범위 밖 질문에 엉뚱한 답을 지어낼 일이 없다.
"""
import re
from datetime import date

from .state import AgentState
from .supervisor import PERSONAL, has_any

INTRO = ("안녕하세요! 저는 청년정책 안내 도우미예요. 나이와 사는 지역, 관심 분야(취업·주거·자산·교육 등)를 "
         "알려주시면 지금 신청할 수 있는 청년정책을 찾아드리고, 청년월세·국민내일배움카드 같은 제도의 "
         "자격 기준과 신청 방법도 안내 자료를 근거로 설명해 드려요.\n"
         "예) \"2002년생 서울 사는데 지금 신청할 수 있는 취업 지원 있어?\"")


# 안내 자료 속 신청 기간 형식 (실제 문서에서 확인한 세 가지)
#   연도 있음: "2026. 3. 30.(월) 09:00 ~ 5. 29.(금) 16:00"  (끝 연도는 생략되기도 함)
#   연도 없음: "(5.4.~5.20.)"   /   한글: "5월 4일부터 5월 20일까지"
# 각 패턴의 그룹: (시작연도, 시작월, 시작일, 끝연도, 끝월, 끝일). 연도가 없는 칸은 문서 연도로 채운다.
PERIODS = [
    re.compile(r"(20\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?[^~\n]{0,20}?~\s*(?:(20\d{2})\.\s*)?(\d{1,2})\.\s*(\d{1,2})"),
    re.compile(r"()(?<![\d.])(\d{1,2})\.\s*(\d{1,2})\.\s*~\s*()(\d{1,2})\.\s*(\d{1,2})\."),
    re.compile(r"()(\d{1,2})월\s*(\d{1,2})일[^~\n]{0,12}?(?:~|부터)\s*()(?:(\d{1,2})월\s*)?(\d{1,2})일"),
]


APPLY_WORDS = ("신청", "접수", "모집")
NOT_APPLY = ("뽑히면", "선정되면", "일해요", "근무", "활동", "지급기간", "사업기간")


def is_apply_period(text: str, start: int, end: int) -> bool:
    """신청 기간만 표시한다. 정책집에는 '뽑히면 10월 1일부터 12월 23일까지 일해요' 같은 근무 기간도 있어서
    (실제 문서 확인) 이를 '진행 중'으로 표시하면 지금 신청할 수 있다고 잘못 안내할 수 있다."""
    before, after = text[max(0, start - 30):start], text[end:end + 40]   # "~까지 ○○ 신규 모집" 처럼 뒤에 오기도 함
    near = text[max(0, start - 15):start] + text[end:end + 20]
    return any(w in before or w in after for w in APPLY_WORDS) and not any(w in near for w in NOT_APPLY)


def period_notes(text: str, today: str, year: int | None = None) -> list[str]:
    """문서 속 기간을 오늘과 비교한다. 날짜 계산은 작은 LLM이 자주 틀려서(실행 중 확인) 코드가 한다."""
    try:
        t = date.fromisoformat(today)
    except ValueError:
        return []
    year = year or t.year
    found, used = [], []                            # used: 이미 잡은 글자 범위 (같은 기간을 두 번 세지 않게)
    for pat in PERIODS:
        for m in pat.finditer(text):
            if any(m.start() < e and s < m.end() for s, e in used):
                continue
            y1, m1, d1, y2, m2, d2 = m.groups()
            try:
                start = date(int(y1 or year), int(m1), int(d1))
                end = date(int(y2 or start.year), int(m2 or m1), int(d2))
                if not y2 and end < start:          # "12. 1. ~ 1. 15." → 끝은 다음 해
                    end = end.replace(year=end.year + 1)
            except ValueError:                      # 13월 같은 잘못된 날짜는 건너뜀
                continue
            used.append((m.start(), m.end()))
            if is_apply_period(text, m.start(), m.end()):
                found.append((m.start(), m.group(), start, end))
    notes = []
    for _, raw, start, end in sorted(found):
        status = "이미 지났음" if t > end else ("진행 중" if t >= start else "아직 시작 전")
        notes.append(f"'{' '.join(raw.split())}' = {start}~{end} → 오늘({t}) 기준 {status}")
    return notes


def _facts(state: AgentState, today: str, data_date: str) -> tuple[str, list[str]]:
    lines, sources = [f"- 오늘 날짜: {today} / 정책 데이터 기준일: {data_date}"], []
    if state.get("age"):
        lines.append(f"- 사용자 나이: {state['age']['text']}")
    if state.get("region_info"):
        lines.append(f"- 사용자 지역: {state['region_info']['지역']}")
    pr = state.get("policy_result")
    if pr is not None:
        lines.append(f"\n[조건에 맞는 신청 가능 정책] 총 {pr['총개수']}개 중 상위 {len(pr['정책'])}개")
        for x in pr["정책"]:
            lines.append(f"- {x['정책명']} | 지역: {x['지역']} | 주관: {x['주관기관']} | 신청상태: {x['신청상태']} "
                         f"| 신청기간: {x['신청기간']} | 대상연령: {x['대상연령']}\n  지원내용: {x['지원내용']}\n"
                         f"  신청방법: {x['신청방법']} | 신청주소: {x['신청주소']}")
            sources.append(f"온통청년 정책: {x['정책명']}")
        for x in pr.get("마감된_관련정책", []):
            lines.append(f"- (마감) {x['정책명']} | 지역: {x['지역']} | 신청상태: 마감 | 신청기간: {x['신청기간']}")
            sources.append(f"온통청년 정책: {x['정책명']}")
    dr = state.get("doc_result")
    if dr is not None:
        lines.append(f"\n[안내 자료 발췌] (검색 결과가 질문에 충분한지: {'충분' if dr['enough'] else '부족 - ' + dr['reason']})")
        for c in dr["chunks"]:
            label = " · ".join(x for x in (f"발행: {c['issuer']}" if c.get("issuer") else "",
                                           f"적용 지역: {c['region']}" if c.get("region") else "") if x)
            lines.append(f"({c['source']} {c['page']}쪽{' · ' + label if label else ''})\n{c['text']}")
            for note in period_notes(c["text"], today, c.get("year")):
                lines.append(f"[기간 확인] {note}")
            sources.append(f"{c['source']} {c['page']}쪽")
    if has_any(state["question"], PERSONAL) and not state.get("age") and not state.get("region_info"):
        lines.append("\n- 참고: 사용자가 나이·지역을 알려주지 않았다. 답변 끝에 알려주면 더 정확히 찾을 수 있다고 안내할 것.")
    return "\n".join(lines), list(dict.fromkeys(sources))     # 순서 유지하며 중복 제거


def clean(text: str) -> str:
    """qwen3가 생각 과정(<think>...</think>)을 섞어 내는 경우를 대비해 지운다."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


async def write_node(state: AgentState, deps) -> dict:
    today = await deps.mcp.call_tool("get_today", {})                          # MCP Tool
    catalog = await deps.mcp.read_catalog()                                   # MCP Resource
    facts, sources = _facts(state, str(today), catalog["데이터_기준일"])
    prompt = await deps.mcp.get_answer_prompt(state["question"], facts)       # MCP Prompt
    reply = await deps.llm.ainvoke(prompt)
    return {"answer": clean(reply.content), "sources": sources, "path": ["write"], "llm_calls": 1}


async def chat_node(state: AgentState, deps) -> dict:
    return {"answer": INTRO, "sources": [], "path": ["chat"], "llm_calls": 0}


async def clarify_node(state: AgentState, deps) -> dict:
    return {"answer": ("정확히 찾아드리려면 몇 가지만 알려주세요.\n"
                       "1) 출생 연도(예: 2002년생) 또는 나이\n2) 사는 지역(예: 서울, 전북 전주)\n"
                       "3) 관심 분야(취업, 주거, 자산 형성, 교육 등)\n"
                       "예) \"2002년생 전주 사는데 주거 지원 있어?\""),
            "sources": [], "path": ["clarify"], "llm_calls": 0}
