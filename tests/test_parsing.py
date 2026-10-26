from datetime import datetime, time

import pytest

from bot.schedule_parser import ScheduleParseError, parse_csv, parse_text, parse_xlsx
from bot.text_utils import parse_due, split_subject


def test_parse_text_basic():
    lessons = parse_text(
        "Пн 09:00-10:30 Математика | ауд. 101 | Иванов И.И.\n"
        "Вторник\n"
        "10.45–12.15 Физика\n"
        "13:00-14:30 История | 305\n"
    )
    assert len(lessons) == 3
    assert lessons[0].weekday == 0 and lessons[0].room == "ауд. 101" and lessons[0].teacher == "Иванов И.И."
    assert lessons[1].weekday == 1 and lessons[1].start == time(10, 45) and lessons[1].subject == "Физика"
    assert lessons[2].room == "305"


def test_parse_text_errors():
    with pytest.raises(ScheduleParseError):
        parse_text("09:00-10:30 Математика")
    with pytest.raises(ScheduleParseError):
        parse_text("Пн Математика")


def test_parse_csv_with_header_and_split_times():
    data = "День;Начало;Конец;Предмет;Аудитория\nПн;09:00;10:30;Математика;101\n;10:45;12:15;Физика;\n".encode()
    lessons = parse_csv(data)
    assert [l.subject for l in lessons] == ["Математика", "Физика"]
    assert lessons[1].weekday == 0 and lessons[0].room == "101"


def test_parse_xlsx():
    import io
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["День", "Время", "Предмет", "Аудитория", "Преподаватель"])
    ws.append(["Ср", "09:00-10:30", "Химия", "12", "Петров"])
    ws.append(["Пт", time(11, 0), time(12, 30), "Биология"])
    buf = io.BytesIO()
    wb.save(buf)
    lessons = parse_xlsx(buf.getvalue())
    assert lessons[0].weekday == 2 and lessons[0].teacher == "Петров"
    assert lessons[1].weekday == 4 and lessons[1].start == time(11, 0)


def test_split_subject():
    assert split_subject("Математика: решить №5") == ("Математика", "решить №5")
    assert split_subject("просто текст") == ("", "просто текст")


NOW = datetime(2026, 10, 26, 12, 0)


@pytest.mark.parametrize("text,body,due", [
    ("сдать лабу до 30.10 18:00", "сдать лабу", datetime(2026, 10, 30, 18, 0)),
    ("эссе завтра", "эссе", datetime(2026, 10, 27, 23, 59)),
    ("доклад к 05.01", "доклад", datetime(2027, 1, 5, 23, 59)),
    ("купить тетради", "купить тетради", None),
    ("завтра", "завтра", None),
])
def test_parse_due(text, body, due):
    assert parse_due(text, NOW) == (body, due)


ICS = b"""BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VEVENT\r
DTSTART:20261026T040000Z\r
DTEND:20261026T053000Z\r
SUMMARY:\xd0\x9c\xd0\xb0\xd1\x82\xd0\xb5\xd0\xbc\xd0\xb0\xd1\x82\xd0\xb8\xd0\xba\xd0\xb0\r
LOCATION:\xd0\xb0\xd1\x83\xd0\xb4. 101\\, \xd0\xba\xd0\xbe\xd1\x80\xd0\xbf\xd1\x83\xd1\x81 2\r
END:VEVENT\r
BEGIN:VEVENT\r
DTSTART:20261102T040000Z\r
DTEND:20261102T053000Z\r
SUMMARY:\xd0\x9c\xd0\xb0\xd1\x82\xd0\xb5\xd0\xbc\xd0\xb0\xd1\x82\xd0\xb8\xd0\xba\xd0\xb0\r
END:VEVENT\r
BEGIN:VEVENT\r
DTSTART;TZID=Europe/Moscow:20261027T120000\r
DURATION:PT1H20M\r
SUMMARY:Physics lecture with a very long title that is\r
  folded\r
END:VEVENT\r
BEGIN:VEVENT\r
DTSTART;VALUE=DATE:20261028\r
SUMMARY:Holiday\r
END:VEVENT\r
BEGIN:VEVENT\r
DTSTART:20261029T090000\r
SUMMARY:Cancelled\r
STATUS:CANCELLED\r
END:VEVENT\r
END:VCALENDAR\r
"""


def test_parse_ics():
    from bot.schedule_parser import parse_ics

    lessons = parse_ics(ICS, "Asia/Tashkent")
    assert len(lessons) == 2  # повтор схлопнут, весь день и отменённое пропущены
    math, phys = lessons
    assert (math.weekday, math.start, math.end) == (0, time(9, 0), time(10, 30))
    assert math.subject == "Математика" and math.room == "ауд. 101, корпус 2"
    # 12:00 по Москве = 14:00 по Ташкенту
    assert (phys.weekday, phys.start, phys.end) == (1, time(14, 0), time(15, 20))
    assert phys.subject.endswith("is folded")


def test_parse_ics_empty():
    from bot.schedule_parser import parse_ics

    with pytest.raises(ScheduleParseError):
        parse_ics(b"BEGIN:VCALENDAR\nEND:VCALENDAR\n", "Asia/Tashkent")
