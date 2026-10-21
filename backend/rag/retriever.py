from collections import Counter
from pathlib import Path

from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

ROOT = Path(__file__).resolve().parents[2]
DB_DIR = ROOT / "vectorstore"

_db = Chroma(persist_directory=str(DB_DIR), collection_name="policies",
             embedding_function=OllamaEmbeddings(model="bge-m3"))


def search(query: str, k: int = 3):
    """질문과 가장 가까운 청크 k개를 (문서, 거리) 쌍으로 돌려준다. 거리는 작을수록 가까움."""
    return _db.similarity_search_with_score(query, k=k)


if __name__ == "__main__":
    # ① 메타데이터 점검: 문서별·지역별로 청크가 몇 개씩 들어갔는지
    metas = _db.get()["metadatas"]
    print("문서별:", Counter(m["source"] for m in metas))
    print("지역별:", Counter(m["region"] for m in metas))

    # ② 검색 점검: 질문을 넣고 나온 조각을 직접 읽어보기
    for q in ["월세 지원 받으려면 소득 기준이 어떻게 돼?", "국민내일배움카드로 뭘 할 수 있어?"]:
        print(f"\n===== 질문: {q}")
        for doc, score in search(q):
            m = doc.metadata
            print(f"[{m['source']} {m['page']}쪽 | 거리 {score:.3f}]")
            print(doc.page_content[:150].replace("\n", " "), "...")