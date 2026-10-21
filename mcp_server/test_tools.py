import pytest

from tools import (age_ok, age_range_ok, application_status, calc_age, catalog,
                   find_policies, region_of, resolve_region)


def test_calc_age(monkeypatch):
    monkeypatch.setenv("FAKE_TODAY", "2026-10-21")        # 오늘을 고정
    assert calc_age(2002, 11, 5) == {"만나이": 23}          # 생일 전
    assert calc_age(2002, 10, 21) == {"만나이": 24}         # 생일 당일
    assert calc_age(2002)["만나이_최소"] == 23


def test_application_status(monkeypatch):
    monkeypatch.setenv("FAKE_TODAY", "2026-10-21")
    assert application_status({"aplyPrdSeCd": "0057002"}) == "상시"
    assert application_status({"aplyPrdSeCd": "0057003"}) == "마감"
    period = lambda ymd: {"aplyPrdSeCd": "0057001", "aplyYmd": ymd}
    assert application_status(period("20261019 ~ 20261030")) == "신청중"
    assert application_status(period("20261101 ~ 20261130")) == "신청예정"
    assert application_status(period("20260301 ~ 20260331")) == "마감"
    assert application_status(period("20260101 ~ 20260131\n20261001 ~ 20261031")) == "신청중"  # 기간 두 줄
    assert application_status(period("20261001 ~ 20261031\\N20261201 ~ 20261231")) == "신청중"  # 실제 데이터 형식(글자 \N)


def test_age_ok():
    rng = lambda yn, lo, hi: {"sprtTrgtAgeLmtYn": yn, "sprtTrgtMinAge": lo, "sprtTrgtMaxAge": hi}
    assert age_ok(rng("Y", "0", "0"), 50)          # 나이 정보 없음 → 통과
    assert not age_ok(rng("Y", "18", "39"), 45)    # Y라도 범위가 있으면 지킨다 (실제 680개)
    assert age_ok(rng("N", "19", "34"), 24)
    assert not age_ok(rng("N", "19", "34"), 35)
    assert age_ok(rng("N", "0", "0"), 24)          # N인데 0~0 → 통과 (실제 63개)
    assert age_ok(rng("N", "18", "0"), 50)         # 최대 0 = 상한 없음
    assert age_ok(rng("N", "", ""), 24)            # 빈 값


def test_age_range_ok():
    p = {"sprtTrgtMinAge": "19", "sprtTrgtMaxAge": "23"}
    assert age_range_ok(p, 23, 24)            # 23세일 수도 있으면 포함 (생일 전)
    assert not age_range_ok(p, 24, 25)
    assert age_range_ok(p, 20)                # 범위 없이 한 나이만


NATION = ",".join(str(11000 + i) for i in range(250))       # 코드 250개 = 전국


def test_region_of():
    assert region_of({"zipCd": NATION}) == "전국"
    assert region_of({"zipCd": "52111,52113"}) == "전북특별자치도 전주시"
    assert region_of({"zipCd": "12210,12240,12270,12300,12330"}) == "광주광역시"
    assert region_of({"zipCd": "12780"}) == "전라남도 강진군"       # 광주와 같은 앞자리 12지만 전남


def test_resolve_region():
    assert resolve_region("전주")["지역"] == "전북특별자치도 전주시"
    assert resolve_region("전주")["codes"] == {"52111", "52113"}
    assert resolve_region("광주")["지역"] == "광주광역시"
    assert resolve_region("경기 광주시")["지역"] == "경기도 광주시"     # 광주광역시와 구분
    assert resolve_region("서울")["단위"] == "시도"
    assert resolve_region("수원")["시도"] == "경기"                   # 표에 없는 도시는 도 단위로
    assert resolve_region("강남")["시도"] == "서울"
    assert resolve_region("없는지역") is None
    assert resolve_region("청년월세 받으려면 소득 기준이 어떻게 돼?") is None   # 지역 없는 질문
    assert resolve_region("") is None and resolve_region(None) is None


def test_find_policies_region(monkeypatch):
    monkeypatch.setenv("FAKE_TODAY", "2026-10-21")
    r = find_policies(region="전주", only_open=False, limit=100000)
    regions = {x["지역"] for x in r["정책"]}
    assert "전북특별자치도 전주시" in regions                       # 전주시 정책이 나온다 (전엔 0개)
    assert not any("군산시" in x or "익산시" in x for x in regions)   # 같은 도의 다른 시 정책은 안 나온다
    assert r["조건"]["지역단위"] == "시군구"
    with pytest.raises(ValueError):                                  # 모르는 지역 → 조용히 무시하지 않고 오류
        find_policies(region="없는지역")


def test_find_policies_order_and_dedupe(monkeypatch):
    monkeypatch.setenv("FAKE_TODAY", "2026-10-21")
    r = find_policies(age=24, only_open=True, limit=100000)
    order = {"신청중": 0, "상시": 1, "신청예정": 2}
    is_local = [x["지역"] != "전국" for x in r["정책"]]
    assert is_local == sorted(is_local)                              # 지역을 모르면 전국 정책이 먼저
    for local in (False, True):                                      # 각 묶음 안에서는 상태 순
        statuses = [order[x["신청상태"]] for x in r["정책"] if (x["지역"] != "전국") == local]
        assert statuses == sorted(statuses)
    k = find_policies(age=24, keyword="월세", limit=100000)["정책"]
    in_name = ["월세" in x["정책명"] for x in k]
    assert in_name == sorted(in_name, reverse=True)                  # 이름에 키워드 있는 정책이 먼저
    names = [x["정책명"] for x in r["정책"]]
    assert len(names) == len(set(names))                             # 같은 이름은 하나만
    assert r["총개수"] == len(r["정책"])
    assert all(x["신청상태"] != "마감" for x in r["정책"])


def test_catalog():
    c = catalog()
    assert c["전체_정책수"] == 3472
    assert "취업" in c["분야_목록"] and not any("," in x for x in c["분야_목록"])
