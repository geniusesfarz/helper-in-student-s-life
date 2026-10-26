from datetime import timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from ..db import Database
from ..keyboards import BTN_SCHEDULE, BTN_TODAY, BTN_TOMORROW, BTN_WEEK, MAIN_MENU
from ..schedule_parser import (
    WEEKDAY_NAMES,
    ScheduleParseError,
    parse_csv,
    parse_ics,
    parse_text,
    parse_xlsx,
)
from ..timeutil import local_now

router = Router()


class ScheduleUpload(StatesGroup):
    waiting = State()


UPLOAD_HELP = (
    "Пришли расписание <b>одним сообщением</b>, по паре в строке:\n\n"
    "<code>Пн 09:00-10:30 Математика | ауд. 101 | Иванов И.И.\n"
    "Пн 10:45-12:15 Физика | ауд. 204\n"
    "Вт 09:00-10:30 История</code>\n\n"
    "Аудитория и преподаватель необязательны. Можно написать день отдельной строкой, "
    "а под ним пары без дня.\n\n"
    "Или пришли файл <b>Excel (.xlsx) или CSV</b> с колонками: "
    "день, время (09:00-10:30), предмет, аудитория, преподаватель.\n\n"
    "Или файл календаря <b>.ics</b> (экспорт из Google Календаря, Outlook или с сайта вуза): "
    "пары из него соберу в расписание на неделю.\n\n"
    "Новое расписание заменит старое. /cancel — отмена."
)


def format_lesson(row) -> str:
    line = f"<b>{row['start']}–{row['end']}</b> {escape(row['subject'])}"
    extra = ", ".join(escape(x) for x in (row["room"], row["teacher"]) if x)
    return f"{line}\n      {extra}" if extra else line


async def day_text(db: Database, user_id: int, weekday: int, title: str) -> str:
    lessons = await db.lessons_for_day(user_id, weekday)
    if not lessons:
        return f"<b>{title}</b>\nПар нет 🎉"
    return f"<b>{title}</b>\n" + "\n".join(format_lesson(l) for l in lessons)


async def _user_tz(db: Database, user_id: int, default_tz: str) -> str:
    await db.ensure_user(user_id, default_tz)
    return (await db.get_user(user_id))["tz"]


@router.message(Command("schedule"))
@router.message(F.text == BTN_SCHEDULE)
async def ask_schedule(message: Message, state: FSMContext):
    await state.set_state(ScheduleUpload.waiting)
    await message.answer(UPLOAD_HELP)


@router.message(StateFilter(ScheduleUpload.waiting), F.document)
async def schedule_file(message: Message, state: FSMContext, db: Database, bot: Bot, default_tz: str):
    name = (message.document.file_name or "").lower()
    data = (await bot.download(message.document)).read()
    try:
        if name.endswith(".xlsx"):
            lessons = parse_xlsx(data)
        elif name.endswith(".csv"):
            lessons = parse_csv(data)
        elif name.endswith(".ics"):
            lessons = parse_ics(data, await _user_tz(db, message.from_user.id, default_tz))
        elif name.endswith(".txt"):
            lessons = parse_text(data.decode("utf-8-sig", errors="replace"))
        else:
            await message.answer("Поддерживаются файлы .ics, .xlsx, .csv и .txt.")
            return
    except ScheduleParseError as e:
        await message.answer(f"Не смог разобрать файл:\n{escape(str(e))}\n\nИсправь и пришли снова или /cancel.")
        return
    await _save(message, state, db, lessons, default_tz)


@router.message(StateFilter(ScheduleUpload.waiting), F.text)
async def schedule_text(message: Message, state: FSMContext, db: Database, default_tz: str):
    try:
        lessons = parse_text(message.text)
    except ScheduleParseError as e:
        await message.answer(f"Не смог разобрать:\n{escape(str(e))}\n\nИсправь и пришли снова или /cancel.")
        return
    await _save(message, state, db, lessons, default_tz)


async def _save(message: Message, state: FSMContext, db: Database, lessons, default_tz: str):
    await db.ensure_user(message.from_user.id, default_tz)
    await db.replace_schedule(message.from_user.id, lessons)
    await state.clear()
    days = len({l.weekday for l in lessons})
    await message.answer(
        f"Сохранил расписание: {len(lessons)} пар, {days} дн. в неделю ✅\nПосмотреть: /week",
        reply_markup=MAIN_MENU,
    )


@router.message(Command("today"))
@router.message(F.text == BTN_TODAY)
async def today(message: Message, db: Database, default_tz: str):
    now = local_now(await _user_tz(db, message.from_user.id, default_tz))
    wd = now.weekday()
    await message.answer(await day_text(db, message.from_user.id, wd, f"Сегодня, {WEEKDAY_NAMES[wd].lower()}"))


@router.message(Command("tomorrow"))
@router.message(F.text == BTN_TOMORROW)
async def tomorrow(message: Message, db: Database, default_tz: str):
    now = local_now(await _user_tz(db, message.from_user.id, default_tz)) + timedelta(days=1)
    wd = now.weekday()
    await message.answer(await day_text(db, message.from_user.id, wd, f"Завтра, {WEEKDAY_NAMES[wd].lower()}"))


@router.message(Command("week"))
@router.message(F.text == BTN_WEEK)
async def week(message: Message, db: Database, default_tz: str):
    await db.ensure_user(message.from_user.id, default_tz)
    lessons = await db.all_lessons(message.from_user.id)
    if not lessons:
        await message.answer("Расписание пока пустое. Загрузи его: /schedule")
        return
    blocks = []
    for wd in range(7):
        day = [l for l in lessons if l["weekday"] == wd]
        if day:
            blocks.append(f"<b>{WEEKDAY_NAMES[wd]}</b>\n" + "\n".join(format_lesson(l) for l in day))
    await message.answer("\n\n".join(blocks))
