"""맥의 PyMuPDF(2.0)에서 표 찾기가 어떻게 동작하는지 확인 (전주 청년월세 3쪽)."""
import sys
import unicodedata
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
f = [p for p in (ROOT / "data" / "raw").glob("*.pdf") if "월세" in unicodedata.normalize("NFC", p.stem)][0]
print("pymupdf", pymupdf.__version__, "| python", sys.version.split()[0])
print("layout 모듈:", [m for m in sys.modules if "layout" in m.lower()][:5])
page = pymupdf.open(f)[2]
for kw in ({}, {"strategy": "lines"}, {"strategy": "lines_strict"}, {"strategy": "text"}):
    try:
        ts = page.find_tables(**kw).tables
        print(kw, "→ 표", len(ts), [(t.row_count, t.col_count) for t in ts])
        for t in ts[:2]:
            print("   ", t.extract()[:3])
    except Exception as e:
        print(kw, "오류", repr(e))
print("drawings(선) 개수:", len(page.get_drawings()))
