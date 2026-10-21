import json
import os
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICIES = json.loads((ROOT / "data" / "raw" / "policies.json").read_text(encoding="utf-8"))
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
    # "YYYYMMDD ~ YYYYMMDD" 쌍을 모두 찾는다. 기간이 두 개인 정책은 줄바꿈 대신
    # 글자 그대로 "\\N"으로 이어져 있어서(데이터로 확인) 줄 단위로 나누면 깨진다.
    periods = re.findall(r"(\d{8})\s*~\s*(\d{8})", p.get("aplyYmd", ""))
    for start, end in periods:
        if start <= today <= end:
            return "신청중"
    if any(today < start for start, _ in periods):
        return "신청예정"
    return "마감"


def region_of(p: dict) -> str:
    if p.get("pvsnInstGroupCd") == CENTRAL:
        return "전국"
    return p.get("rgtrHghrkInstCdNm") or p.get("sprvsnInstCdNm") or "알수없음"


def age_ok(p: dict, age: int) -> bool:
    """나이 조건 판단. sprtTrgtAgeLmtYn(Y/N) 칸은 실제 나이 값과 맞지 않는 경우가 많아서
    (전수 확인: Y인데 범위가 있는 정책 680개, N인데 0~0인 정책 63개) 무시하고 숫자만 본다."""
    lo = int(p.get("sprtTrgtMinAge") or 0)
    hi = int(p.get("sprtTrgtMaxAge") or 0)
    if lo == 0 and hi == 0:                 # 나이 정보 없음 → 제한 없는 것으로 본다
        return True
    return lo <= age <= (hi if hi > 0 else 999)   # 최대가 0이면 상한 없음


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


def catalog() -> dict:
    """정책 데이터 안내판: 기준일, 전체 수, 분야 목록, 신청상태별 개수"""
    from collections import Counter
    return {
        "데이터_기준일": "2026-10-21",
        "전체_정책수": len(POLICIES),
        # 분야가 "취업,창업"처럼 여러 개 붙어 있는 정책이 있어서 쉼표로 나눠 하나씩 모은다
        "분야_목록": sorted({name.strip() for p in POLICIES
                         for name in p.get("mclsfNm", "").split(",") if name.strip()}),
        "신청상태별_개수": dict(Counter(application_status(p) for p in POLICIES)),
    }
