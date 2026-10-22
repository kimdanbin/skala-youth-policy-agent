"""FastAPI 테스트 — 진짜 MCP·Ollama 없이 가짜 그래프를 끼워서 /chat 응답 모양과 오류 처리를 검사한다.
TestClient를 'with' 없이 쓰면 lifespan(MCP 서버 띄우기)이 실행되지 않는다."""
from fastapi.testclient import TestClient

import main
from agent.deps import Deps
from agent.graph import ERROR_MESSAGE, build_graph
from agent.state import Plan
from test_agent import FakeLLM, FakeMCP, FakeSearch


def client_with(plans, **mcp_kw):
    main.app.state.graph = build_graph(Deps(llm=FakeLLM(plans), mcp=FakeMCP(**mcp_kw), search=FakeSearch()))
    return TestClient(main.app)


def test_health():
    assert TestClient(main.app).get("/health").json() == {"status": "ok"}


def test_chat_returns_answer_and_trace(monkeypatch):
    monkeypatch.setenv("FAKE_TODAY", "2026-10-21")
    c = client_with([Plan(route="chat")])
    r = c.post("/chat", json={"message": "안녕"})
    body = r.json()
    assert r.status_code == 200 and body["ok"] is True
    assert body["path"] == ["supervisor", "chat"] and body["llm_calls"] == 1
    assert "청년정책 안내" in body["reply"] and set(body) >= {"reply", "sources", "path", "llm_calls", "elapsed_sec"}


def test_chat_error_is_friendly_not_500(monkeypatch):
    c = client_with([Plan(route="both")], fail_catalog=True)
    r = c.post("/chat", json={"message": "청년월세 기준 알려줘"})
    assert r.status_code == 200 and r.json()["ok"] is False and r.json()["reply"] == ERROR_MESSAGE


def test_chat_validates_body():
    r = TestClient(main.app).post("/chat", json={"msg": "틀린 칸"})
    assert r.status_code == 422                                   # Pydantic 검증


def test_cors_allows_vue_origin():
    r = TestClient(main.app).options("/chat", headers={"Origin": "http://localhost:5173",
                                                       "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
