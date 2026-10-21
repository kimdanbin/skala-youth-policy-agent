"""③ 문서검색 서브에이전트 — RAG 검색 → LLM 채점 → 부족하면 검색어를 바꿔 다시 (Corrective RAG).

3-B에서 본 실패(월세 '소득 기준' 질문에 자격요건 3쪽 대신 선발 점수 4쪽을 가져와 반쪽 답을 함)를
고치려는 단계다. 단순 RAG는 '가져온 게 맞는지' 확인하지 않지만, 여기서는 LLM이 채점한다.
"""
import asyncio

from .state import DOC_K, MAX_DOC_RETRY, MAX_DOC_RETRY_BOTH, AgentState, Grade
from .supervisor import PROGRAM_HINTS

GRADE_SYSTEM = """너는 검색 결과 채점자다. [찾을 정보]가 [문서 조각]에 들어 있는지 판단하라.
- [찾을 정보]의 핵심(예: 자격 기준, 금액, 서류, 지원 내용)이 조각에 구체적으로 적혀 있으면 enough=true
- 사용자 개인이 자격이 되는지 최종 판단은 하지 않는다. 판단에 필요한 기준이 적혀 있으면 enough=true
- 관련은 있지만 핵심이 빠졌거나 다른 이야기(예: 기준이 아니라 선발 방법)면 enough=false
- enough=false면 reason에 무엇이 빠졌는지 쓰고, better_query에 다시 찾을 더 구체적인 검색 문장을 써라"""


def _chunks(results) -> list[dict]:
    return [{"source": d.metadata.get("source"), "program": d.metadata.get("program"),
             "page": d.metadata.get("page"), "distance": round(float(s), 3), "text": d.page_content}
            for d, s in results]


def _render(chunks: list[dict]) -> str:
    return "\n\n".join(f"({c['source']} {c['page']}쪽)\n{c['text']}" for c in chunks)


async def grade(deps, question: str, chunks: list[dict], need: str | None = None) -> Grade | None:
    if not chunks:
        return Grade(enough=False, reason="검색 결과 0개", better_query=None)
    try:
        return await deps.llm.with_structured_output(Grade).ainvoke(
            [("system", GRADE_SYSTEM),
             ("human", f"[사용자 질문]\n{question}\n\n[찾을 정보]\n{need or question}\n\n[문서 조각]\n{_render(chunks)}")])
    except Exception:
        return None


async def doc_node(state: AgentState, deps) -> dict:
    plan, question = state["plan"], state["question"]
    query = plan.get("doc_query") or question
    program = plan.get("doc_program")
    hint = next((v for k, v in PROGRAM_HINTS.items() if k in question), None)
    tried, llm_calls, chunks, g = [], 0, [], None
    max_retry = MAX_DOC_RETRY_BOTH if plan.get("route") == "both" else MAX_DOC_RETRY
    for attempt in range(max_retry + 1):
        # Chroma 검색은 동기 함수라 그대로 부르면 기다리는 동안 서버 전체가 멈춘다 → 별도 스레드에서
        results = await asyncio.to_thread(deps.search, query, DOC_K, program)
        chunks = _chunks(results)
        g = await grade(deps, question, chunks, plan.get("doc_query"))
        llm_calls += 1 if chunks else 0
        tried.append({"검색어": query, "문서": program, "충분": None if g is None else g.enough,
                      "가져온 쪽": [f"{c['program']} {c['page']}" for c in chunks]})
        if g is None:                                  # 채점 실패 → 무한히 돌지 않고 지금 결과로 진행
            break
        if g.enough or attempt == max_retry:
            break
        # 다음 검색 준비: 더 구체적인 검색어 + 문서 범위 조정
        query = (g.better_query or "").strip() or f"{question} {plan.get('keyword') or ''}".strip()
        if attempt == 0 and program is None and hint:  # 질문에 '월세' 등이 있으면 그 문서 안에서
            program = hint
        elif attempt == 1 and program is not None:    # 그래도 안 되면 필터를 풀고 전체에서
            program = None
    enough = bool(g and g.enough)
    return {"doc_result": {"chunks": chunks, "enough": enough,
                           "reason": g.reason if g else "채점 실패(LLM 응답 형식 오류)",
                           "시도": tried},
            "path": ["doc_agent"], "llm_calls": llm_calls,
            "notes": [f"문서검색 {len(tried)}회: " + " → ".join(str(t["충분"]) for t in tried)]}
