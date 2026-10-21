import unicodedata
from pathlib import Path

import pymupdf
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
import shutil

ROOT = Path(__file__).resolve().parents[2]      # 프로젝트 최상위 폴더
RAW_DIR = ROOT / "data" / "raw"                  # PDF가 있는 곳
DB_DIR = ROOT / "vectorstore"                    # 벡터 DB를 저장할 곳 (.gitignore에 있음)
CENTRAL_AGENCIES = {"고용노동부", "보건복지부", "국토교통부"}   # 전국 대상 문서를 내는 곳


def load_pdfs() -> list[Document]:
    docs = []
    for pdf_path in sorted(RAW_DIR.glob("*.pdf")):
        # 맥은 한글 파일명을 자모 분리 형태(NFD)로 저장해서, 합쳐진 형태(NFC)로 바꿔줌
        name = unicodedata.normalize("NFC", pdf_path.stem)
        year, program, issuer = name.split("_")
        region = "전국" if issuer in CENTRAL_AGENCIES else issuer
        pdf = pymupdf.open(pdf_path)
        for page_num, page in enumerate(pdf, start=1):
            text = page.get_text().strip()
            if len(text) < 50:                   # 표지·빈 페이지는 건너뜀
                continue
            docs.append(Document(
                page_content=text,
                metadata={"source": name, "page": page_num, "year": year,
                          "program": program, "issuer": issuer, "region": region},
            ))
    return docs


def main():
    shutil.rmtree(DB_DIR, ignore_errors=True)   # 기존 벡터 DB 삭제 후 새로 만들기
    pages = load_pdfs()
    print(f"페이지 {len(pages)}개 읽음")

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(pages)     # 메타데이터는 조각마다 그대로 복사됨
    print(f"청크 {len(chunks)}개로 자름")

    embeddings = OllamaEmbeddings(model="bge-m3")
    Chroma.from_documents(chunks, embeddings,
                          persist_directory=str(DB_DIR), collection_name="policies")
    print(f"벡터 DB 저장 완료 → {DB_DIR}")


if __name__ == "__main__":
    main()