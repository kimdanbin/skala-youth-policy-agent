"""PDF 표 추출 (원본 PDF가 있을 때만: data/raw는 git에 올리지 않음)"""
import unicodedata
from pathlib import Path

import pymupdf
import pytest

from rag.ingest import NUM, page_text

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"


def _pdf(name):
    for f in RAW.glob("*.pdf"):
        if unicodedata.normalize("NFC", f.stem) == name:
            return pymupdf.open(f)
    pytest.skip(f"{name}.pdf 없음")


def test_table_keeps_columns():
    """전주 청년월세 3쪽: 청년가구/원가구 칸이 한 줄에 살아 있어야 한다 (평가 D2에서 원가구 기준이 빠지던 원인)"""
    text = page_text(_pdf("2026_청년월세_전주시")[2])
    flat = text.replace(" ", "")                     # 칸 안 띄어쓰기는 PyMuPDF 버전마다 달라서 빼고 비교
    assert "|구분|ⓐ청년가구|ⓑ원가구|" in flat
    assert "|ⓓ재산가액|1.22억원이하|4.7억원이하|" in flat
    assert "자격요건" in text and "원가구 소득·재산은 고려하지 않음" in text     # 표 밖 글자도 그대로
    assert "2026년 기준 중위소득" in text                                       # 표 바로 위 줄도 살아 있어야 함


def test_page_without_table_unchanged():
    page = _pdf("2026_청년월세_전주시")[0]
    assert page_text(page) == page.get_text().strip()


def test_no_number_lost_on_any_page():
    """모든 페이지에서 원래 글자의 숫자가 표 변환 뒤에도 그대로 있어야 한다 (맥 PyMuPDF 2.0 소수점 문제 방지)"""
    files = list(RAW.glob("*.pdf"))
    if not files:
        pytest.skip("PDF 없음")
    for f in files:
        for page in pymupdf.open(f):
            plain, text = page.get_text(), page_text(page)
            assert set(NUM.findall(plain)) <= set(NUM.findall(text)), (f.name, page.number + 1)
