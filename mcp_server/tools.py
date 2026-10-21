"""청년정책 판단 도구 (MCP를 모르는 순수 함수 모음 — pytest로 바로 테스트한다).

데이터: data/raw/policies.json (온통청년 API, 2026-10-21 기준 3,472개)
여기 적힌 데이터 관련 규칙은 전부 실제 데이터를 전수로 세어 보고 정한 것이다.
"""
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICIES = json.loads((ROOT / "data" / "raw" / "policies.json").read_text(encoding="utf-8"))
DATA_DATE = "2026-10-21"


# ───────────────────────── 날짜·나이 ─────────────────────────

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


def age_ok(p: dict, age: int) -> bool:
    """나이 조건 판단. sprtTrgtAgeLmtYn(Y/N) 칸은 실제 나이 값과 맞지 않는 경우가 많아서
    (전수 확인: Y인데 범위가 있는 정책 680개, N인데 0~0인 정책 63개) 무시하고 숫자만 본다."""
    lo = int(p.get("sprtTrgtMinAge") or 0)
    hi = int(p.get("sprtTrgtMaxAge") or 0)
    if lo == 0 and hi == 0:                 # 나이 정보 없음 → 제한 없는 것으로 본다
        return True
    return lo <= age <= (hi if hi > 0 else 999)   # 최대가 0이면 상한 없음


def age_range_ok(p: dict, age: int, age_upper: int | None = None) -> bool:
    """만 나이가 범위(예: 생년만 알 때 23~24)일 때, 그 안의 나이 중 하나라도 맞으면 통과."""
    upper = age if age_upper is None else max(age, age_upper)
    return any(age_ok(p, a) for a in range(age, upper + 1))


# ───────────────────────── 지역 ─────────────────────────
# 지역은 기관 "이름"이 아니라 zipCd(법정 시군구 코드 목록)로 판단한다.
# 이름으로 판단하면 전주시 정책이 "전북특별자치도"로만 적혀 있어 "전주"로 못 찾고,
# 기관명 칸에 "청년정책과" 같은 부서명만 있는 정책(110개)은 지역을 아예 알 수 없었다.
# zipCd는 3,472개 전부에 있다(전수 확인). 규칙: 사용자 지역 코드 ∩ 정책 zipCd ≠ ∅ 이면 해당.

def policy_codes(p: dict) -> set[str]:
    return {c.strip() for c in p.get("zipCd", "").split(",") if c.strip()}


ALL_CODES = set().union(*(policy_codes(p) for p in POLICIES))
NATIONWIDE_MIN = 200          # 코드가 200개 이상이면 전국 대상으로 본다 (전체 고유 코드 262개)

# 이 데이터에서는 광주광역시와 전라남도가 "전남광주통합특별시"로 묶여 둘 다 앞자리 12를 쓴다.
# 광주광역시·광주시청 정책이 쓰는 코드 5개가 광주의 5개 구다(데이터로 확인).
GWANGJU_CODES = {"12210", "12240", "12270", "12300", "12330"}

SIDO = {   # 표준 키: (표시 이름, 코드 앞 두 자리)
    "서울": ("서울특별시", "11"), "부산": ("부산광역시", "26"), "대구": ("대구광역시", "27"),
    "인천": ("인천광역시", "28"), "광주": ("광주광역시", "12"), "대전": ("대전광역시", "30"),
    "울산": ("울산광역시", "31"), "세종": ("세종특별자치시", "36"), "경기": ("경기도", "41"),
    "충북": ("충청북도", "43"), "충남": ("충청남도", "44"), "전북": ("전북특별자치도", "52"),
    "전남": ("전라남도", "12"), "경북": ("경상북도", "47"), "경남": ("경상남도", "48"),
    "제주": ("제주특별자치도", "50"), "강원": ("강원특별자치도", "51"),
}
SIDO_ALIASES = {   # 사용자가 쓸 법한 이름 → 표준 키
    **{k: k for k in SIDO},
    "서울특별시": "서울", "서울시": "서울", "부산광역시": "부산", "부산시": "부산",
    "대구광역시": "대구", "대구시": "대구", "인천광역시": "인천", "인천시": "인천",
    "광주광역시": "광주", "대전광역시": "대전", "대전시": "대전", "울산광역시": "울산", "울산시": "울산",
    "세종특별자치시": "세종", "세종시": "세종", "경기도": "경기",
    "충청북도": "충북", "충청남도": "충남", "전라북도": "전북", "전북특별자치도": "전북",
    "전라남도": "전남", "경상북도": "경북", "경상남도": "경남",
    "제주특별자치도": "제주", "제주도": "제주", "강원도": "강원", "강원특별자치도": "강원",
}
PREFIX_TO_SIDO = {v[1]: k for k, v in SIDO.items() if k != "광주"}   # "12" → 전남 (광주는 따로)

# 시(市) 이름만 말했을 때 어느 도인지 알기 위한 표 (행정구역 상식).
# 데이터에서 만든 시군구 표(SIGUNGU)에 없는 도시(예: 수원)도 최소한 "경기도"로는 찾게 하려는 것.
# "광주"(광주광역시/경기 광주시)와 "제주"(도/시)는 겹쳐서 일부러 뺐다 → 시도 별칭으로 처리.
CITY_TO_SIDO = {
    **dict.fromkeys("수원 성남 의정부 안양 부천 광명 평택 동두천 안산 고양 과천 구리 남양주 오산 시흥 "
                    "군포 의왕 하남 용인 파주 이천 안성 김포 화성 양주 포천 여주".split(), "경기"),
    **dict.fromkeys("춘천 원주 강릉 동해 태백 속초 삼척".split(), "강원"),
    **dict.fromkeys("청주 충주 제천".split(), "충북"),
    **dict.fromkeys("천안 공주 보령 아산 서산 논산 계룡 당진".split(), "충남"),
    **dict.fromkeys("전주 군산 익산 정읍 남원 김제".split(), "전북"),
    **dict.fromkeys("목포 여수 순천 나주 광양".split(), "전남"),
    **dict.fromkeys("포항 경주 김천 안동 구미 영주 영천 상주 문경 경산".split(), "경북"),
    **dict.fromkeys("창원 진주 통영 사천 김해 밀양 거제 양산".split(), "경남"),
    "서귀포": "제주",
    # 서울 자치구(데이터의 시군구 표에는 서울 구가 거의 없다). 중구처럼 여러 시에 있는 이름은 뺐다.
    **dict.fromkeys("종로 용산 성동 광진 동대문 중랑 성북 강북 도봉 노원 은평 서대문 마포 양천 "
                    "강서 구로 금천 영등포 동작 관악 서초 강남 송파 강동".split(), "서울"),
}


def code_sido(code: str) -> str:
    return "광주" if code in GWANGJU_CODES else PREFIX_TO_SIDO.get(code[:2], "알수없음")


def sido_codes(sido: str) -> set[str]:
    return {c for c in ALL_CODES if code_sido(c) == sido}


_NAME_FIELDS = ("rgtrInstCdNm", "sprvsnInstCdNm", "rgtrUpInstCdNm", "operInstCdNm")
_SIGUNGU_PAT = re.compile(r"(\S{1,6}?(?:시|군|구))(?=\s|$|\()")


def _build_sigungu_table() -> dict[tuple[str, str], set[str]]:
    """(시도, 시군구 이름) → 코드 묶음. 데이터에서 만든다: 코드가 1~6개인 정책 중 기관명에
    그 시군구 이름이 있는 정책들에서, 절반 이상 함께 나오는 코드를 그 시군구의 코드로 본다.
    (예: 전주시 → 52111, 52113 / 창원시 → 48121~48129) 표에 없는 시군구는 시도 단위로 찾는다."""
    hits: dict = defaultdict(Counter)
    count: Counter = Counter()
    for p in POLICIES:
        codes = policy_codes(p)
        if not 1 <= len(codes) <= 6:
            continue
        sidos = {code_sido(c) for c in codes}
        if len(sidos) != 1:
            continue
        sido = sidos.pop()
        names = set()
        for f in _NAME_FIELDS:
            for m in _SIGUNGU_PAT.finditer(p.get(f) or ""):
                name = m.group(1)
                if not name.endswith(("특별시", "광역시", "특별자치시")) and len(name) >= 2:
                    names.add(name)
        for name in names:
            if SIDO_ALIASES.get(name) == sido or SIDO_ALIASES.get(name[:-1]) == sido:
                continue   # "대전시", "서울시"처럼 광역시 자기 이름은 시군구가 아니다 (경기 "광주시"는 남김)
            count[(sido, name)] += 1
            hits[(sido, name)].update(codes)
    table = {}
    for key, c in hits.items():
        codes = {code for code, n in c.items() if n >= 0.5 * count[key]}
        if codes:
            table[key] = codes
    return table


SIGUNGU = _build_sigungu_table()
CODE_TO_SIGUNGU = {}
for (_sido, _name), _codes in SIGUNGU.items():
    for _c in _codes:
        CODE_TO_SIGUNGU.setdefault(_c, (_sido, _name))


def resolve_region(text: str | None) -> dict | None:
    """'전주', '서울 강남구', '경기 광주시', '광주' 같은 글을 지역 코드 묶음으로 바꾼다.
    인식 못 하면 None. 시군구가 표에 없으면 시도 단위로 넓혀서 찾는다(정밀도 대신 누락 방지)."""
    if not text or not text.strip():
        return None
    # ① 시도: 글에서 가장 먼저 나오는 별칭 (같은 위치면 긴 것 우선: "광주광역시" > "광주")
    found = [(text.find(a), -len(a), SIDO_ALIASES[a]) for a in SIDO_ALIASES if a in text]
    sido = min(found)[2] if found else None
    # 도시·자치구 이름: 시도를 안 말했으면 이걸로 시도를 알아낸다 ("수원" → 경기, "강남" → 서울)
    hits = sorted((text.find(c), c) for c in CITY_TO_SIDO
                  if c in text and (sido is None or CITY_TO_SIDO[c] == sido))
    city = hits[0][1] if hits else None
    if sido is None and city:
        sido = CITY_TO_SIDO[city]
    # ② 시군구: 전체 이름("전주시") 또는 끝 글자를 뗀 이름("전주", 두 글자 이상일 때만)
    cands = []
    for (s, name), codes in SIGUNGU.items():
        if sido and s != sido:
            continue
        short = name[:-1]
        if name in text or (len(short) >= 2 and short in text and short not in SIDO_ALIASES):
            cands.append((s, name, codes))
    if cands:
        sidos = {c[0] for c in cands}
        codes = set().union(*(c[2] for c in cands))
        if len(sidos) == 1:
            s = sidos.pop()
            label = SIDO[s][0] + " " + "·".join(sorted({c[1] for c in cands}))
            return {"지역": label, "시도": s, "단위": "시군구", "codes": codes}
        return {"지역": "·".join(sorted({SIDO[c[0]][0] + " " + c[1] for c in cands})),
                "시도": None, "단위": "시군구(여러 곳)", "codes": codes}
    if sido:
        label = SIDO[sido][0] + (f" ({city} 단위 정보가 없어 {SIDO[sido][0]} 전체로 찾음)" if city else "")
        return {"지역": label, "시도": sido, "단위": "시도", "codes": sido_codes(sido)}
    return None


def region_of(p: dict) -> str:
    """정책의 대상 지역을 사람이 읽을 이름으로 (zipCd 기준)."""
    codes = policy_codes(p)
    if len(codes) >= NATIONWIDE_MIN:
        return "전국"
    sidos = sorted({code_sido(c) for c in codes})
    if len(sidos) == 1:
        names = {CODE_TO_SIGUNGU.get(c, (None, None))[1] for c in codes}
        if None not in names and len(names) == 1:
            return SIDO[sidos[0]][0] + " " + names.pop()
        return SIDO.get(sidos[0], (sidos[0],))[0]
    return ", ".join(SIDO.get(s, (s,))[0] for s in sidos)


# ───────────────────────── 정책 찾기 ─────────────────────────

STATUS_ORDER = {"신청중": 0, "상시": 1, "신청예정": 2, "마감": 3}


def _relevance(p: dict, keyword: str | None) -> int | None:
    """키워드가 어디에 있는지: 0=정책 이름, 1=키워드·설명, 2=분야 이름에만, None=없음."""
    if not keyword:
        return 0
    if keyword in p.get("plcyNm", ""):
        return 0
    if keyword in p.get("plcyKywdNm", "") or keyword in p.get("plcyExplnCn", ""):
        return 1
    if keyword in p.get("mclsfNm", "") or keyword in p.get("lclsfNm", ""):
        return 2
    return None


def _apply_end(p: dict) -> str:
    ends = re.findall(r"\d{8}\s*~\s*(\d{8})", p.get("aplyYmd", ""))
    return min(ends) if ends else "99999999"


CENTRAL = "0054001"            # 제공기관 그룹코드: 중앙부처


def _summary(p: dict, status: str) -> dict:
    return {"정책명": p["plcyNm"].strip(), "지역": region_of(p),
            "주관기관": p.get("sprvsnInstCdNm") or p.get("rgtrInstCdNm") or "",
            "분야": p.get("mclsfNm"),
            "신청상태": status, "신청기간": p.get("aplyYmd") or status,
            "대상연령": _age_text(p),
            "지원내용": (p.get("plcySprtCn") or "")[:200],
            "신청방법": (p.get("plcyAplyMthdCn") or "")[:100],
            "신청주소": p.get("aplyUrlAddr") or ""}


def _age_text(p: dict) -> str:
    lo = int(p.get("sprtTrgtMinAge") or 0)
    hi = int(p.get("sprtTrgtMaxAge") or 0)
    if lo == 0 and hi == 0:
        return "제한 없음(정보 없음)"
    return f"{lo}세 이상" if hi == 0 else f"{lo}~{hi}세"


def find_policies(age: int | None = None, region: str | None = None,
                  keyword: str | None = None, only_open: bool = True, limit: int = 5,
                  age_upper: int | None = None) -> dict:
    """조건에 맞는 정책을 찾아 정렬해서 돌려준다.
    정렬: 신청중 > 상시 > 신청예정(> 마감), 같은 상태면 마감일이 가까운 순.
    지역을 주면 '그 지역 전용 정책'과 '전국 정책'을 번갈아 섞는다(전국 정책이 결과를 덮지 않게).
    인식할 수 없는 지역을 주면 ValueError (조용히 지역 조건을 빼고 찾지 않는다)."""
    loc = None
    if region:
        loc = resolve_region(region)
        if loc is None:
            raise ValueError(f"지역을 인식하지 못했어요: {region}")
    matched = []
    for p in POLICIES:
        status = application_status(p)
        if only_open and status == "마감":
            continue
        if age is not None and not age_range_ok(p, age, age_upper):
            continue
        if loc and not (policy_codes(p) & loc["codes"]):
            continue
        rel = _relevance(p, keyword)
        if rel is None:
            continue
        matched.append((p, status, rel))

    def key(item):
        p, status, rel = item
        # ① 키워드가 정책 이름에 있는 것 먼저(분야 이름에만 걸린 것은 뒤로: '월세'가 '전월세 및 주거급여
        #    지원' 분야에 걸려 신혼부부 전세대출까지 섞이는 문제 확인) ② 신청중 > 상시 > 신청예정
        # ③ 중앙부처 먼저(지자체가 올린 '전국 대상' 정책보다 일반적) ④ 마감 임박 순
        # 지역을 모르면 전국 정책을 먼저: 남의 지역 정책(예: 청송군 월세지원)은 사용자가 못 받을 수 있다
        other_region = loc is None and len(policy_codes(p)) < NATIONWIDE_MIN
        return (rel, other_region, STATUS_ORDER[status], p.get("pvsnInstGroupCd") != CENTRAL,
                _apply_end(p), p["plcyNm"])

    matched.sort(key=key)
    # 같은 이름의 정책이 여러 기관에 중복 등록된 경우가 있어(전수 확인) 순위가 높은 하나만 남긴다
    seen, unique = set(), []
    for item in matched:
        name = item[0]["plcyNm"].strip()
        if name not in seen:
            seen.add(name)
            unique.append(item)
    matched = unique
    if loc:
        local = [m for m in matched if len(policy_codes(m[0])) < NATIONWIDE_MIN]
        nation = [m for m in matched if len(policy_codes(m[0])) >= NATIONWIDE_MIN]
        # 섞을 때도 관련도는 지킨다: 이름에 키워드가 있는 정책이 먼저 나오도록 관련도별로 섞는다
        mixed = []
        for rel in (0, 1, 2):
            lo = [m for m in local if m[2] == rel]
            na = [m for m in nation if m[2] == rel]
            for i in range(max(len(lo), len(na))):
                mixed += [x[i] for x in (lo, na) if i < len(x)]
        matched = mixed
    return {
        "조건": {"나이": None if age is None else (f"{age}" if not age_upper or age_upper == age else f"{age}~{age_upper}"),
                 "지역": loc["지역"] if loc else None, "지역단위": loc["단위"] if loc else None,
                 "키워드": keyword, "마감제외": only_open},
        "총개수": len(matched),
        "정책": [_summary(p, s) for p, s, _ in matched[:limit]],
    }


def catalog() -> dict:
    """정책 데이터 안내판: 기준일, 전체 수, 분야 목록, 신청상태별 개수"""
    return {
        "데이터_기준일": DATA_DATE,
        "전체_정책수": len(POLICIES),
        # 분야가 "취업,창업"처럼 여러 개 붙어 있는 정책이 있어서 쉼표로 나눠 하나씩 모은다
        "분야_목록": sorted({name.strip() for p in POLICIES
                         for name in p.get("mclsfNm", "").split(",") if name.strip()}),
        "신청상태별_개수": dict(Counter(application_status(p) for p in POLICIES)),
    }
