"""Разбор расписания из текста, CSV и Excel.

Формат строки текста:
    Пн 09:00-10:30 Математика | ауд. 101 | Иванов И.И.
Аудитория и преподаватель необязательны. Строка, состоящая только из дня
недели (например, «Понедельник»), задаёт день для следующих строк без дня.
"""
import csv
import io
import re
from dataclasses import dataclass
from datetime import time

WEEKDAYS = {
    0: ("пн", "пон", "понедельник", "mon", "monday"),
    1: ("вт", "вто", "вторник", "tue", "tuesday"),
    2: ("ср", "сре", "среда", "wed", "wednesday"),
    3: ("чт", "чет", "четверг", "thu", "thursday"),
    4: ("пт", "пят", "пятница", "fri", "friday"),
    5: ("сб", "суб", "суббота", "sat", "saturday"),
    6: ("вс", "вос", "воскресенье", "sun", "sunday"),
}
WEEKDAY_NAMES = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
WEEKDAY_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

_TIME_RANGE = re.compile(r"(\d{1,2})[:.](\d{2})\s*[-–—]\s*(\d{1,2})[:.](\d{2})")


@dataclass
class Lesson:
    weekday: int
    start: time
    end: time
    subject: str
    room: str = ""
    teacher: str = ""


class ScheduleParseError(ValueError):
    pass


def parse_weekday(token: str) -> int | None:
    token = token.strip().lower().rstrip(".,:")
    for day, names in WEEKDAYS.items():
        if token in names:
            return day
    return None


def _parse_time_range(text: str) -> tuple[time, time, str] | None:
    m = _TIME_RANGE.search(text)
    if not m:
        return None
    h1, m1, h2, m2 = map(int, m.groups())
    try:
        start, end = time(h1, m1), time(h2, m2)
    except ValueError:
        return None
    rest = (text[: m.start()] + " " + text[m.end():]).strip()
    return start, end, rest


def parse_text(text: str) -> list[Lesson]:
    lessons: list[Lesson] = []
    errors: list[str] = []
    current_day: int | None = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        first, _, remainder = line.partition(" ")
        day = parse_weekday(first)
        if day is not None:
            current_day = day
            line = remainder.strip()
            if not line:
                continue
        if current_day is None:
            errors.append(f"строка {lineno}: не указан день недели")
            continue
        parsed = _parse_time_range(line)
        if not parsed:
            errors.append(f"строка {lineno}: не нашёл время вида 09:00-10:30")
            continue
        start, end, rest = parsed
        parts = [p.strip() for p in rest.split("|")]
        subject = parts[0] if parts else ""
        if not subject:
            errors.append(f"строка {lineno}: не указан предмет")
            continue
        lessons.append(Lesson(
            weekday=current_day,
            start=start,
            end=end,
            subject=subject,
            room=parts[1] if len(parts) > 1 else "",
            teacher=parts[2] if len(parts) > 2 else "",
        ))
    if errors:
        raise ScheduleParseError("\n".join(errors))
    if not lessons:
        raise ScheduleParseError("не нашёл ни одной пары")
    return lessons


def _rows_to_lessons(rows: list[list[str]]) -> list[Lesson]:
    """Строки таблицы: день, время (09:00-10:30), предмет, аудитория, преподаватель.
    Также допускается: день, начало, конец, предмет, аудитория, преподаватель."""
    lines = []
    for row in rows:
        cells = [str(c).strip() if c is not None else "" for c in row]
        if not any(cells):
            continue
        if parse_weekday(cells[0]) is None and lines == [] and cells[0]:
            continue  # заголовок таблицы
        if len(cells) >= 3 and _parse_time_range(cells[1]) is None and _parse_time_range(f"{cells[1]}-{cells[2]}"):
            cells = [cells[0], f"{cells[1]}-{cells[2]}", *cells[3:]]
        day, tr, *rest = cells + [""] * (3 - len(cells))
        extra = " | ".join(rest).rstrip(" |")
        lines.append(f"{day} {tr} {extra}".strip())
    return parse_text("\n".join(lines))


def parse_csv(data: bytes) -> list[Lesson]:
    text = data.decode("utf-8-sig", errors="replace")
    dialect = csv.Sniffer().sniff(text.splitlines()[0]) if text.strip() else csv.excel
    return _rows_to_lessons(list(csv.reader(io.StringIO(text), dialect)))


def _cell_to_str(value) -> str:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    return "" if value is None else str(value)


def parse_xlsx(data: bytes) -> list[Lesson]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows = [[_cell_to_str(v) for v in row] for row in ws.iter_rows(values_only=True)]
    return _rows_to_lessons(rows)
