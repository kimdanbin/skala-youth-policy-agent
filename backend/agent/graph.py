"""에이전트 그래프: Supervisor → (정책조회 ∥ 문서검색) → 검토·재계획 → 답변.

        ┌──────── supervisor(계획) ────────┐
        │     │        │          │       │
       chat clarify policy_agent doc_agent   (both면 두 서브에이전트를 동시에 실행)
        │     │        └────┬─────┘
       END   END         review ── 부족 → 재계획 → 실패한 서브에이전트만 다시 (최대 MAX_REPLAN회)
                            │ 충분
                          write → END
"""
import asyncio
import time
from functools import partial

from langgraph.graph import END, START, StateGraph

from .doc_agent import doc_node
from .policy_agent import policy_node
from .state import AgentState
from .supervisor import after_plan, after_review, plan_node, review_node
from .writer import chat_node, clarify_node, write_node

RECURSION_LIMIT = 25          # 그래프 전체 단계 수 상한 (무한 루프 3중 방어의 마지막)
TIMEOUT_SEC = 300             # 질문 하나 최대 처리 시간
ERROR_MESSAGE = ("죄송해요, 지금은 답변을 만들 수 없어요. 잠시 후 다시 시도해 주세요. "
                 "급하시면 온통청년(youthcenter.go.kr)에서 직접 확인하실 수 있어요.")


def build_graph(deps):
    g = StateGraph(AgentState)
    node = lambda fn: partial(fn, deps=deps)          # 의존성 주입: 노드는 deps를 밖에서 받는다
    g.add_node("supervisor", node(plan_node))
    g.add_node("chat", node(chat_node))
    g.add_node("clarify", node(clarify_node))
    g.add_node("policy_agent", node(policy_node))
    g.add_node("doc_agent", node(doc_node))
    g.add_node("review", node(review_node))
    g.add_node("write", node(write_node))

    g.add_edge(START, "supervisor")
    g.add_conditional_edges("supervisor", after_plan,
                            ["chat", "clarify", "policy_agent", "doc_agent"])
    g.add_edge("chat", END)
    g.add_edge("clarify", END)
    g.add_edge("policy_agent", "review")
    g.add_edge("doc_agent", "review")
    g.add_conditional_edges("review", after_review, ["policy_agent", "doc_agent", "write"])
    g.add_edge("write", END)
    return g.compile()


async def run(graph, question: str) -> dict:
    """질문 하나 처리. 어떤 오류가 나도 예외를 밖으로 던지지 않고 안내 문구 + error를 돌려준다."""
    started = time.perf_counter()
    try:
        state = await asyncio.wait_for(
            graph.ainvoke({"question": question}, config={"recursion_limit": RECURSION_LIMIT, "run_name": "youth-policy-agent"}),
            timeout=TIMEOUT_SEC)
        error = None
    except Exception as e:                          # 시간 초과·Ollama 꺼짐·MCP 오류 등
        state, error = {}, f"{type(e).__name__}: {e}"
    return {"question": question,
            "answer": state.get("answer") or ERROR_MESSAGE,
            "sources": state.get("sources", []),
            "path": state.get("path", []),
            "llm_calls": state.get("llm_calls", 0),
            "elapsed_sec": round(time.perf_counter() - started, 2),
            "plan": state.get("plan"), "plan_source": state.get("plan_source"),
            "age": state.get("age"), "region": state.get("region_info"),
            "policy_total": (state.get("policy_result") or {}).get("총개수"),
            "doc_pages": [f"{c['program']} {c['page']}" for c in (state.get("doc_result") or {}).get("chunks", [])],
            "doc_enough": (state.get("doc_result") or {}).get("enough"),
            "notes": state.get("notes", []), "error": error}
