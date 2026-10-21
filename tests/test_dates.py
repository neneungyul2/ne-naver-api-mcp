from datetime import datetime, timedelta, timezone

import pytest

from ne_naver_api_mcp.dates import korean_today, resolve_date, resolve_date_range


def kst_today() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d")


def test_korean_today_is_kst_yyyy_mm_dd():
    assert korean_today() == kst_today()
    assert len(korean_today()) == 10 and korean_today()[4] == "-"


def test_korean_today_does_not_double_apply_offsets():
    # UTC 2026-07-26 16:00 == KST 2026-07-27 01:00
    assert korean_today(datetime(2026, 7, 26, 16, 0, tzinfo=timezone.utc)) == "2026-07-27"
    # 다른 시간대로 표현된 같은 순간도 같은 결과
    est = timezone(timedelta(hours=-5))
    assert korean_today(datetime(2026, 7, 26, 11, 0, tzinfo=est)) == "2026-07-27"


def test_naive_datetime_is_treated_as_utc():
    assert korean_today(datetime(2026, 7, 26, 16, 0)) == "2026-07-27"


def test_resolve_date_today_any_case():
    assert resolve_date("today") == kst_today()
    assert resolve_date("TODAY") == kst_today()
    assert resolve_date("Today") == kst_today()


def test_resolve_date_passes_through_valid_dates():
    assert resolve_date("2026-01-01") == "2026-01-01"
    assert resolve_date("2025-12-31") == "2025-12-31"


@pytest.mark.parametrize("bad", ["2026/01/01", "2026-1-1", "tomorrow", "", "20260101"])
def test_resolve_date_rejects_bad_format(bad):
    with pytest.raises(ValueError, match="Invalid date format"):
        resolve_date(bad)


def test_resolve_date_range_resolves_both_sides():
    assert resolve_date_range("2026-01-01", "today") == ("2026-01-01", kst_today())
    assert resolve_date_range("today", "today") == (kst_today(), kst_today())
