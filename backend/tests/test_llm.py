"""LLM 고르기 (실제 호출 없이 객체 종류만 확인)"""
import pytest

import llm


def test_default_is_ollama(monkeypatch):
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    assert type(llm.get_llm()).__name__ == "ChatOllama"


def test_openai_backend(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "OpenAI ")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    m = llm.get_llm()
    assert type(m).__name__ == "ChatOpenAI" and m.model_name == "gpt-4o-mini" and m.max_retries == 4


def test_openai_without_key_fails_clearly(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        llm.get_llm()


def test_unknown_backend(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "gemini")
    with pytest.raises(ValueError, match="지원하지 않는"):
        llm.get_llm()
