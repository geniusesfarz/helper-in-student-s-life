from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def valid_tz(name: str) -> bool:
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def local_now(tz: str) -> datetime:
    """Текущее время пользователя без tzinfo (так хранятся сроки задач)."""
    return datetime.now(ZoneInfo(tz)).replace(tzinfo=None, second=0, microsecond=0)
