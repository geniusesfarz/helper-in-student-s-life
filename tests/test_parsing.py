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
