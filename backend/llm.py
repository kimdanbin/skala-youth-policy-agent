import os

from langchain_ollama import ChatOllama


def get_llm():
    """LLM_BACKEND 환경변수로 Ollama/OpenAI를 고른다. 지금은 Ollama만."""
    backend = os.getenv("LLM_BACKEND", "ollama")
    if backend == "ollama":
        # reasoning=False: qwen3의 <think> 생각 출력을 꺼서 답변이 빨라지고 깔끔해짐
        return ChatOllama(model="qwen3:8b", temperature=0, reasoning=False)
    raise ValueError(f"아직 지원하지 않는 LLM_BACKEND: {backend}")