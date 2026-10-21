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


def test_age_ok():
    assert age_ok({"sprtTrgtAgeLmtYn": "Y", "sprtTrgtMinAge": "0", "sprtTrgtMaxAge": "0"}, 50)  # Y = 제한 없음
    assert age_ok({"sprtTrgtAgeLmtYn": "N", "sprtTrgtMinAge": "19", "sprtTrgtMaxAge": "34"}, 24)
    assert not age_ok({"sprtTrgtAgeLmtYn": "N", "sprtTrgtMinAge": "19", "sprtTrgtMaxAge": "34"}, 35)


def test_region_of():
    assert region_of({"pvsnInstGroupCd": "0054001"}) == "전국"
    assert region_of({"pvsnInstGroupCd": "0054002", "rgtrHghrkInstCdNm": "",
                      "sprvsnInstCdNm": "대구광역시"}) == "대구광역시"   # 빈 칸이면 주관기관으로