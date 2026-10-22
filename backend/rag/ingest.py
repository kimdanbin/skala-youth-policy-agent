import re
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


NUM = re.compile(r"\d[\d,.]*\d|\d")      # 1.22 / 1,538,543 / 30 같은 숫자 덩어리


def _clean(text) -> str:
    return " ".join(str(text or "").split())


def table_md(page, table) -> str:
    """PDF 표 → 마크다운 줄. 표에서는 칸 위치(구조)만 쓰고, 칸 글자는 page.get_text(clip=칸)로 다시 읽는다.
    (맥의 PyMuPDF 2.0은 표 칸 글자를 뽑을 때 소수점·쉼표를 뒤로 밀어 '1.22억'을 '122억'으로 만든다 → 실제 확인)"""
    grid = []
    for row in table.rows:
        grid.append([_clean(page.get_text("text", clip=pymupdf.Rect(c))) if c else "" for c in row.cells])
    keep = [j for j in range(max(map(len, grid), default=0)) if any(j < len(r) and r[j] for r in grid)]
    lines = []
    for r in grid:
        cells = [r[j] if j < len(r) else "" for j in keep]      # 모든 줄이 빈 칸인 열(병합 셀 흔적)은 뺀다
        if len(set(cells)) == 1:                                 # 병합 셀이 칸마다 복사된 줄 → 한 칸으로
            cells = cells[:1]
        if any(cells):
            lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def page_text(page) -> str:
    """페이지 글자를 뽑되, 표는 칸 구조를 살려 마크다운 표로 바꾼다.

    get_text()만 쓰면 표가 한 줄씩 풀려서 '1.22억원 이하 4.7억원 이하'처럼 어느 칸(청년가구/원가구)인지
    사라진다 → 실제 평가에서 원가구 재산 기준(4.7억)을 답변이 계속 빠뜨림(평가 D2). 그래서 표 영역의
    글자 블록은 빼고, 그 자리에 표를 마크다운으로 넣는다. 한 줄짜리 장식용 표는 무시한다.
    안전장치: 원래 글자(get_text)에 있던 숫자가 하나라도 사라지면 표 변환을 버리고 원래 글자를 쓴다.
    """
    plain = page.get_text().strip()
    tables = [t for t in page.find_tables().tables if t.row_count >= 2 and t.col_count >= 2]
    if not tables:
        return plain
    rects = [pymupdf.Rect(t.bbox) for t in tables]
    items = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):      # 글자 줄 단위로: 가운데가 표 안에 있는 줄만 뺀다
            r = pymupdf.Rect(line["bbox"])
            center = pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
            if any(center in tr for tr in rects):
                continue                         # 표 안의 글자 → 아래에서 표로 넣는다
            txt = "".join(span["text"] for span in line["spans"]).strip()
            if txt:
                items.append((r.y0, r.x0, txt))
    for t, tr in zip(tables, rects):
        items.append((tr.y0, tr.x0, "[표]\n" + table_md(page, t)))
    items.sort(key=lambda x: (round(x[0]), x[1]))  # 위→아래, 왼→오 순서
    text = "\n".join(x[2] for x in items if x[2]).strip()
    lost = set(NUM.findall(plain)) - set(NUM.findall(text))
    if lost:
        print(f"  [표 변환 취소] {page.parent.name.split('/')[-1]} {page.number + 1}쪽: 숫자 {sorted(lost)[:5]} 사라짐")
        return plain
    return text


def load_pdfs() -> list[Document]:
    docs = []
    for pdf_path in sorted(RAW_DIR.glob("*.pdf")):
        # 맥은 한글 파일명을 자모 분리 형태(NFD)로 저장해서, 합쳐진 형태(NFC)로 바꿔줌
        name = unicodedata.normalize("NFC", pdf_path.stem)
        year, program, issuer = name.split("_")
        region = "전국" if issuer in CENTRAL_AGENCIES else issuer
        pdf = pymupdf.open(pdf_path)
        for page_num, page in enumerate(pdf, start=1):
            text = page_text(page)
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