"""FastAPI 서버 — 화면(Vue)과 에이전트를 잇는 API.

- 서버가 켜질 때(lifespan) MCP 서버 연결·부품·그래프를 '한 번만' 만들고 모든 요청이 같이 쓴다.
  (요청마다 MCP 서버를 새로 띄우면 매번 몇 초씩 걸린다)
- /chat       : 에이전트 (Step 5)
- /chat/basic : 단순 RAG (Step 3, Before 비교용으로 남겨 둠)
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")   # OPENAI_API_KEY, LLM_BACKEND, LANGSMITH_* (import보다 먼저)

from fastapi import FastAPI, Request   # noqa: E402
from fastapi.middleware.cors import CORSMiddleware   # noqa: E402
from pydantic import BaseModel   # noqa: E402

from agent.deps import build_real_deps   # noqa: E402
from agent.graph import ERROR_MESSAGE, build_graph, run   # noqa: E402
from agent.mcp_tools import McpTools   # noqa: E402

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 여기서 실패하면(벡터 DB 없음, MCP 서버 오류 등) 서버가 아예 안 켜지고 원인이 출력된다 → 조용한 실패 방지
    async with McpTools() as mcp:
        app.state.graph = build_graph(build_real_deps(mcp))
        log.info("에이전트 준비 완료 (MCP 서버 연결됨)")
        yield
    log.info("MCP 서버 연결 종료")


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat(req: ChatRequest, request: Request):
    r = await run(request.app.state.graph, req.message)
    if r["error"]:
        log.error("에이전트 오류: %s | 질문: %s", r["error"], req.message)   # 자세한 원인은 서버 로그에만
    return {"reply": r["answer"], "sources": r["sources"], "path": r["path"],
            "llm_calls": r["llm_calls"], "elapsed_sec": r["elapsed_sec"], "ok": r["error"] is None}


@app.post("/chat/basic")
def chat_basic(req: ChatRequest):
    """Before 버전(단순 RAG). 일반 def라서 FastAPI가 별도 스레드에서 돌려 서버가 멈추지 않는다."""
    from rag.chain import answer
    try:
        return {**answer(req.message), "ok": True}
    except Exception as e:
        log.error("단순 RAG 오류: %s", e)
        return {"reply": ERROR_MESSAGE, "sources": [], "ok": False}
