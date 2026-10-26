"""Разбор свободного текста задач и заметок."""
import re
from datetime import date, datetime, time, timedelta

_DUE = re.compile(
    r"\s*(?:до|к|deadline|дедлайн)?\s*"
    r"(?P<day>сегодня|завтра|послезавтра|\d{1,2}\.\d{1,2}(?:\.\d{2,4})?)"
    r"(?:\s+(?:в\s+)?(?P<h>\d{1,2})[:.](?P<m>\d{2}))?\s*$",
    re.IGNORECASE,
)
DEFAULT_DUE_TIME = time(23, 59)


def split_subject(text: str) -> tuple[str, str]:
    """«Математика: решить задачи» -> («Математика», «решить задачи»)."""
    head, sep, tail = text.partition(":")
    if sep and head.strip() and tail.strip() and len(head) <= 60 and "\n" not in head:
        return head.strip(), tail.strip()
    return "", text.strip()


def parse_due(text: str, now: datetime) -> tuple[str, datetime | None]:
    """Отрезает срок в конце текста: «сдать лабу до 30.10 18:00», «эссе завтра»."""
    m = _DUE.search(text)
    if not m or m.start() == 0:
        return text.strip(), None
    day_s = m.group("day").lower()
    today = now.date()
    if day_s == "сегодня":
        d = today
    elif day_s == "завтра":
        d = today + timedelta(days=1)
    elif day_s == "послезавтра":
        d = today + timedelta(days=2)
    else:
        parts = [int(p) for p in day_s.split(".")]
        year = parts[2] if len(parts) == 3 else today.year
        if year < 100:
            year += 2000
        try:
            d = date(year, parts[1], parts[0])
        except ValueError:
            return text.strip(), None
        if len(parts) == 2 and d < today - timedelta(days=30):
            d = d.replace(year=year + 1)
    t = DEFAULT_DUE_TIME
    if m.group("h"):
        try:
            t = time(int(m.group("h")), int(m.group("m")))
        except ValueError:
            return text.strip(), None
    return text[: m.start()].strip(), datetime.combine(d, t)


def format_due(due: datetime, now: datetime) -> str:
    days = (due.date() - now.date()).days
    hm = due.strftime("%H:%M")
    if days == 0:
        return f"сегодня {hm}"
    if days == 1:
        return f"завтра {hm}"
    if days < 0:
        return f"просрочено ({due.strftime('%d.%m')} {hm})"
    return due.strftime("%d.%m %H:%M")
