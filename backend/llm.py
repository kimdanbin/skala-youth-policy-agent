import os

# 기본 모델 이름. 바꾸고 싶으면 .env에 OPENAI_MODEL / OLLAMA_MODEL 을 적는다.
OPENAI_MODEL = "gpt-4o-mini"
OLLAMA_MODEL = "qwen3:8b"


def get_llm():
    """LLM_BACKEND 환경변수(.env)로 LLM을 고른다: ollama(로컬, 기본값) / openai.

    에이전트 코드는 이 함수가 돌려준 객체의 .ainvoke() / .with_structured_output() 만 쓰므로
    어느 쪽이든 그대로 동작한다 (의존성 주입: build_real_deps가 이 함수를 부른다).
    """
    backend = os.getenv("LLM_BACKEND", "ollama").strip().lower()
    if backend == "ollama":
        from langchain_ollama import ChatOllama
        # reasoning=False: qwen3의 <think> 생각 출력을 꺼서 답변이 빨라지고 깔끔해짐
        return ChatOllama(model=os.getenv("OLLAMA_MODEL", OLLAMA_MODEL), temperature=0, reasoning=False)
    if backend == "openai":
        from langchain_openai import ChatOpenAI
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("LLM_BACKEND=openai 인데 .env에 OPENAI_API_KEY가 없습니다")
        # 반 공용 키라 호출이 몰리면 429(요청 한도 초과)가 날 수 있다.
        # max_retries: openai SDK가 429·일시 오류를 점점 길게 기다리며 자동 재시도한다.
        return ChatOpenAI(model=os.getenv("OPENAI_MODEL", OPENAI_MODEL), temperature=0,
                          max_retries=4, timeout=60)
    raise ValueError(f"지원하지 않는 LLM_BACKEND: {backend} (ollama 또는 openai)")
