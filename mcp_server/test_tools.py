from tools import age_ok, application_status, calc_age, region_of


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


def test_region_of():
    assert region_of({"pvsnInstGroupCd": "0054001"}) == "전국"
    assert region_of({"pvsnInstGroupCd": "0054002", "rgtrHghrkInstCdNm": "",
                      "sprvsnInstCdNm": "대구광역시"}) == "대구광역시"   # 빈 칸이면 주관기관으로