import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")                         # .env의 YOUTH_API_KEY 읽기
API_KEY = os.environ["YOUTH_API_KEY"]
URL = "https://www.youthcenter.go.kr/go/ythip/getPlcy"
OUT = ROOT / "data" / "raw" / "policies.json"      # git 제외 폴더에 저장
PAGE_SIZE = 100
PAGES_DIR = ROOT / "data" / "raw" / "policy_pages"   # 페이지별 임시 저장 폴더


def fetch_page(page_num: int) -> dict:
    params = {"apiKeyNm": API_KEY, "pageNum": page_num,
              "pageSize": PAGE_SIZE, "rtnType": "json"}
    for attempt in range(4):                          # 처음 1번 + 재시도 3번
        res = httpx.get(URL, params=params, timeout=30)
        if res.status_code in (403, 429, 500, 502, 503, 504):   # 막힘 또는 서버 일시 오류
            wait = 10 * (2 ** attempt)                # 10초 → 20초 → 40초 → 80초
            print(f"  {page_num}페이지 차단됨({res.status_code}), {wait}초 후 재시도")
            time.sleep(wait)
            continue
        res.raise_for_status()
        return res.json()["result"]
    raise RuntimeError(f"{page_num}페이지: 재시도해도 계속 차단됨. 몇 분 뒤 다시 실행하세요.")


def main():
    PAGES_DIR.mkdir(exist_ok=True)
    first = fetch_page(1)
    total = int(first["pagging"]["totCount"])
    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    print(f"전체 {total}개, {pages}페이지")

    for page in range(1, pages + 1):
        page_file = PAGES_DIR / f"page_{page:02d}.json"
        if page_file.exists():                         # 이미 받은 페이지는 건너뜀
            continue
        items = first["youthPolicyList"] if page == 1 else fetch_page(page)["youthPolicyList"]
        page_file.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        print(f"{page}/{pages} 페이지 저장 ({len(items)}개)")
        time.sleep(1.0)                                # 1초씩 쉬기

    policies = []                                      # 페이지 파일들을 하나로 합치기
    for page_file in sorted(PAGES_DIR.glob("page_*.json")):
        policies += json.loads(page_file.read_text(encoding="utf-8"))
    OUT.write_text(json.dumps(policies, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(policies)}개 저장 → {OUT}")

if __name__ == "__main__":
    main()