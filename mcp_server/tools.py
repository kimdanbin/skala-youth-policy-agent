import json
import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICIES = json.loads((ROOT / "data" / "raw" / "policies.json").read_text())
CENTRAL = "0054001"                       # 제공기관 그룹코드: 중앙부처


def get_today() -> date:
    """오늘 날짜. 평가할 때는 FAKE_TODAY=2026-10-21 처럼 고정할 수 있다(의존성 주입)."""
    fake = os.getenv("FAKE_TODAY")
    return date.fromisoformat(fake) if fake else date.today()


def calc_age(birth_year: int, birth_month: int = 0, birth_day: int = 0) -> dict:
    """만 나이. 생년만 알면 생일 전/후에 따라 두 값이 가능하니 범위로 돌려준다."""
    today = get_today()
    if not birth_month or not birth_day:
        return {"만나이_최소": today.year - birth_year - 1, "만나이_최대": today.year - birth_year,
                "설명": "생일이 지났으면 최대, 안 지났으면 최소"}
    before_birthday = (today.month, today.day) < (birth_month, birth_day)
    return {"만나이": today.year - birth_year - int(before_birthday)}


def application_status(p: dict) -> str:
    """신청 상태: 상시 / 신청중 / 신청예정 / 마감"""
    code = p.get("aplyPrdSeCd")
    if code == "0057002":
        return "상시"
    if code == "0057003":
        return "마감"
    today = get_today().strftime("%Y%m%d")
    periods = [line.split("~") for line in p.get("aplyYmd", "").splitlines() if "~" in line]
    for start, end in periods:
        if start.strip() <= today <= end.strip():
            return "신청중"
    if any(today < start.strip() for start, _ in periods):
        return "신청예정"
    return "마감"


def region_of(p: dict) -> str:
    if p.get("pvsnInstGroupCd") == CENTRAL:
        return "전국"
    return p.get("rgtrHghrkInstCdNm") or p.get("sprvsnInstCdNm") or "알수없음"


def age_ok(p: dict, age: int) -> bool:
    if p.get("sprtTrgtAgeLmtYn") == "Y":   # 주의: Y = 나이 제한 없음 (데이터로 확인)
        return True
    return int(p["sprtTrgtMinAge"] or 0) <= age <= int(p["sprtTrgtMaxAge"] or 999)


def find_policies(age: int | None = None, region: str | None = None,
                  keyword: str | None = None, only_open: bool = True, limit: int = 10) -> list[dict]:
    """조건에 맞는 정책 목록. region은 '서울', '전주' 처럼 일부만 써도 된다(전국 정책은 항상 포함)."""
    results = []
    for p in POLICIES:
        status = application_status(p)
        if only_open and status == "마감":
            continue
        if age is not None and not age_ok(p, age):
            continue
        r = region_of(p)
        if region and r != "전국" and region not in r:
            continue
        text = " ".join([p.get("plcyNm", ""), p.get("plcyKywdNm", ""),
                         p.get("plcyExplnCn", ""), p.get("mclsfNm", "")])
        if keyword and keyword not in text:
            continue
        results.append({"정책명": p["plcyNm"], "지역": r, "분야": p.get("mclsfNm"),
                        "신청상태": status, "신청기간": p.get("aplyYmd") or status,
                        "지원내용": p.get("plcySprtCn", "")[:200],
                        "신청방법": p.get("plcyAplyMthdCn", "")[:100],
                        "신청주소": p.get("aplyUrlAddr", "")})
        if len(results) >= limit:
            break
    return results