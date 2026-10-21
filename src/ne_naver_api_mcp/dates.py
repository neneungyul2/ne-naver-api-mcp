"""날짜 인자 처리: "today"는 한국 표준시(KST) 오늘로 바꾼다."""
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_KST = ZoneInfo("Asia/Seoul")
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def korean_today(now: datetime | None = None) -> str:
    """KST 기준 오늘(yyyy-mm-dd). 호스트 시간대와 무관하다. tz 없는 datetime은 UTC로 본다."""
    moment = now if now is not None else datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(_KST).strftime("%Y-%m-%d")


def resolve_date(value: str) -> str:
    if value.lower() == "today":
        return korean_today()
    if _DATE_RE.match(value):
        return value
    raise ValueError(f'Invalid date format: "{value}". Use "today" or yyyy-mm-dd format.')


def resolve_date_range(start: str, end: str) -> tuple[str, str]:
    return resolve_date(start), resolve_date(end)
