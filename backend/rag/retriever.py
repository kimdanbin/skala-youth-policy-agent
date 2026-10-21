import os
from collections import Counter
from pathlib import Path

from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma

ROOT = Path(__file__).resolve().parents[2]
# 기본은 프로젝트의 vectorstore/. 테스트 등에서 다른 복사본을 쓰고 싶을 때만 VECTORSTORE_DIR로 바꾼다.
DB_DIR = Path(os.getenv("VECTORSTORE_DIR") or ROOT / "vectorstore")

# 조용한 실패 방지: Chroma는 폴더나 데이터가 없어도 에러 없이 "빈 DB"를 새로 만든다.
# 그러면 검색 결과가 항상 0개라 모든 답이 "찾지 못했어요"가 되는데, 에러가 안 나서 원인을
# 찾기 어렵다. 그래서 서버가 켜질 때 바로 확인하고, 문제가 있으면 이유와 해결 방법을 알려주며 멈춘다.
if not DB_DIR.exists():
    raise FileNotFoundError(
        f"벡터 DB 폴더가 없습니다: {DB_DIR}\n"
        "먼저 프로젝트 최상위 폴더에서 `python backend/rag/ingest.py`를 실행하세요.")

_db = Chroma(persist_directory=str(DB_DIR), collection_name="policies",
             embedding_function=OllamaEmbeddings(model="bge-m3"))

if not _db.get(limit=1)["ids"]:
    raise RuntimeError(
        "벡터 DB가 비어 있습니다(청크 0개). data/raw/에 PDF가 있는지 확인하고 "
        "`python backend/rag/ingest.py`를 다시 실행하세요. "
        "(collection_name이 ingest.py와 다를 때도 이렇게 됩니다)")


def search(query: str, k: int = 3, program: str | None = None):
    """질문과 가장 가까운 청크 k개를 (문서, 거리) 쌍으로 돌려준다. 거리는 작을수록 가까움.
    program을 주면 그 사업 문서 안에서만 찾는다(예: "청년월세"). 기본값 None = 전체 (chain.py와 호환)."""
    flt = {"program": program} if program else None
    return _db.similarity_search_with_score(query, k=k, filter=flt)


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