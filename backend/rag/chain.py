from langchain_core.prompts import ChatPromptTemplate

from llm import get_llm
from rag.retriever import search

PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "너는 청년정책 안내 도우미다. 아래 [자료]에 있는 내용만 근거로 한국어로 답하라. "
     "자료에 없는 내용은 '안내 자료에서 찾지 못했어요'라고 답하라. "
     "답변 끝에 참고한 자료를 (문서명 쪽수) 형식으로 적어라."),
    ("human", "[자료]\n{context}\n\n[질문]\n{question}"),
])


def answer(question: str) -> dict:
    results = search(question, k=3)                       # ① 가까운 조각 3개
    context = "\n\n".join(                                # ② [자료] 덩어리 만들기
        f"({doc.metadata['source']} {doc.metadata['page']}쪽)\n{doc.page_content}"
        for doc, _ in results
    )
    chain = PROMPT | get_llm()                            # ③ 프롬프트 → LLM
    reply = chain.invoke({"context": context, "question": question})
    sources = [f"{doc.metadata['source']} {doc.metadata['page']}쪽" for doc, _ in results]
    return {"reply": reply.content, "sources": sources}   # ④ 답 + 출처