"""⑤ 답변 쓰기 / ⑥ 바로 답변 / ⑦ 되묻기.

답변 규칙은 MCP Prompt(policy_answer_prompt)에서 받아온다 → 규칙을 서버 한 곳에서 관리.
⑥⑦은 LLM 없이 정해진 문구: 빠르고, 범위 밖 질문에 엉뚱한 답을 지어낼 일이 없다.
"""
import re

from .state import AgentState
from .supervisor import PERSONAL, has_any

INTRO = ("안녕하세요! 저는 청년정책 안내 도우미예요. 나이와 사는 지역, 관심 분야(취업·주거·자산·교육 등)를 "
         "알려주시면 지금 신청할 수 있는 청년정책을 찾아드리고, 청년월세·국민내일배움카드 같은 제도의 "
         "자격 기준과 신청 방법도 안내 자료를 근거로 설명해 드려요.\n"
         "예) \"2002년생 서울 사는데 지금 신청할 수 있는 취업 지원 있어?\"")


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
            lines.append(f"({c['source']} {c['page']}쪽)\n{c['text']}")
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
