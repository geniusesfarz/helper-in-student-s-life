from datetime import datetime, timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ..db import Database
from ..keyboards import BTN_SCHEDULE, BTN_TODAY, BTN_TOMORROW, BTN_WEEK, MAIN_MENU, inline
from ..render import DayBlock, render_schedule
from ..schedule_parser import (
    WEEKDAY_NAMES,
    WEEKDAY_SHORT,
    ScheduleParseError,
    parse_csv,
    parse_ics,
    parse_text,
    parse_xlsx,
)
from ..text_utils import format_due
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


MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def plural_pairs(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} пара"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} пары"
    return f"{n} пар"


def format_lesson(row) -> str:
    line = f"<b>{row['start']}–{row['end']}</b>  {escape(row['subject'])}"
    extra = " · ".join(escape(x) for x in (row["room"], row["teacher"]) if x)
    return f"{line}\n<i>{extra}</i>" if extra else line


async def day_text(db: Database, user_id: int, weekday: int, title: str) -> str:
    lessons = await db.lessons_for_day(user_id, weekday)
    if not lessons:
        return f"<b>{title}</b>\nПар нет, свободный день"
    return f"<b>{title}</b>\n" + "\n".join(format_lesson(l) for l in lessons)


async def day_view(db: Database, user_id: int, now: datetime, offset: int):
    """Расписание на день (сегодня + offset) с переходом по дням под сообщением."""
    day = now + timedelta(days=offset)
    wd = day.weekday()
    lessons = await db.lessons_for_day(user_id, wd)
    title = f"<b>{WEEKDAY_NAMES[wd]}, {day.day} {MONTHS_GEN[day.month - 1]}</b>"
    when = {0: "Сегодня", 1: "Завтра", -1: "Вчера"}.get(offset)
    if lessons:
        summary = f"{plural_pairs(len(lessons))} · {lessons[0]['start']}–{lessons[-1]['end']}"
        body = "\n\n".join(format_lesson(l) for l in lessons)
    else:
        summary, body = "Пар нет", "Свободный день"
    head = f"{title}\n{when} · {summary}" if when else f"{title}\n{summary}"
    text = f"{head}\n\n{body}"

    if offset == 0:
        tasks = [t for t in await db.open_tasks(user_id) if t["due"]]
        if tasks:
            t = tasks[0]
            subj = f"{escape(t['subject'])}: " if t["subject"] else ""
            due = format_due(datetime.fromisoformat(t["due"]), now)
            text += f"\n\nДедлайн: <b>{subj}{escape(t['text'])}</b> — {due}"

    prev_wd, next_wd = WEEKDAY_SHORT[(wd - 1) % 7], WEEKDAY_SHORT[(wd + 1) % 7]
    kb = inline([
        [(f"‹ {prev_wd}", f"day:{offset - 1}"), ("Неделя", "week"), (f"{next_wd} ›", f"day:{offset + 1}")],
        [("🖼 Картинкой", f"img:{offset}")],
    ])
    return text, kb


async def week_text(db: Database, user_id: int) -> str:
    lessons = await db.all_lessons(user_id)
    if not lessons:
        return "Расписание пока пустое. Загрузи его: /schedule"
    blocks = []
    for wd in range(7):
        day = [l for l in lessons if l["weekday"] == wd]
        if day:
            blocks.append(f"<b>{WEEKDAY_NAMES[wd]}</b>\n" + "\n".join(format_lesson(l) for l in day))
    return "\n\n".join(blocks)


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
        f"Сохранил расписание: {len(lessons)} пар, {days} дн. в неделю.\nПосмотреть: /week",
        reply_markup=MAIN_MENU,
    )


WEEK_KB = inline([[("‹ К сегодня", "day:0"), ("🖼 Картинкой", "img:week")]])


async def _send_day(message: Message, db: Database, default_tz: str, offset: int):
    now = local_now(await _user_tz(db, message.from_user.id, default_tz))
    text, kb = await day_view(db, message.from_user.id, now, offset)
    await message.answer(text, reply_markup=kb)


@router.message(Command("today"))
@router.message(F.text == BTN_TODAY)
async def today(message: Message, db: Database, default_tz: str):
    await _send_day(message, db, default_tz, 0)


@router.message(Command("tomorrow"))
@router.message(F.text == BTN_TOMORROW)
async def tomorrow(message: Message, db: Database, default_tz: str):
    await _send_day(message, db, default_tz, 1)


@router.message(Command("week"))
@router.message(F.text == BTN_WEEK)
async def week(message: Message, db: Database, default_tz: str):
    await db.ensure_user(message.from_user.id, default_tz)
    await message.answer(await week_text(db, message.from_user.id), reply_markup=WEEK_KB)


@router.callback_query(F.data.startswith("day:"))
async def day_cb(call: CallbackQuery, db: Database, default_tz: str):
    offset = max(-30, min(30, int(call.data[4:])))
    now = local_now(await _user_tz(db, call.from_user.id, default_tz))
    text, kb = await day_view(db, call.from_user.id, now, offset)
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "week")
async def week_cb(call: CallbackQuery, db: Database, default_tz: str):
    await db.ensure_user(call.from_user.id, default_tz)
    text = await week_text(db, call.from_user.id)
    await call.message.edit_text(text, reply_markup=WEEK_KB)
    await call.answer()


def _current_lesson_id(lessons, now) -> int | None:
    hm = now.strftime("%H:%M")
    return next((l["id"] for l in lessons if l["start"] <= hm < l["end"]), None)


async def build_image(db: Database, user_id: int, tz: str, kind: str) -> bytes | None:
    now = local_now(tz)
    subjects = sorted({l["subject"] for l in await db.all_lessons(user_id)})
    monday = now.date() - timedelta(days=now.weekday())

    def block(d, lessons):
        is_today = d == now.date()
        return DayBlock(
            title=f"{WEEKDAY_SHORT[d.weekday()]} {d.day}",
            lessons=lessons,
            highlight=is_today and kind == "week",
            current_lesson_id=_current_lesson_id(lessons, now) if is_today else None,
        )

    if kind != "week":
        # день: today, tomorrow или сдвиг от сегодня в днях («-1», «3»)
        offset = {"today": 0, "tomorrow": 1}.get(kind)
        offset = int(kind) if offset is None else offset
        d = now.date() + timedelta(days=offset)
        lessons = await db.lessons_for_day(user_id, d.weekday())
        when = {0: "Сегодня", 1: "Завтра", -1: "Вчера"}.get(offset)
        title = f"{when}, {WEEKDAY_NAMES[d.weekday()].lower()}" if when else f"{WEEKDAY_NAMES[d.weekday()]}, {d:%d.%m}"
        return render_schedule(title, [block(d, lessons)], subjects)

    days = []
    for i in range(7):
        d = monday + timedelta(days=i)
        lessons = await db.lessons_for_day(user_id, d.weekday())
        if lessons:
            days.append(block(d, lessons))
    if not days:
        return None
    sunday = monday + timedelta(days=6)
    return render_schedule(f"Неделя {monday:%d.%m} – {sunday:%d.%m}", days, subjects)


@router.callback_query(F.data.startswith("img:"))
async def send_image(call: CallbackQuery, db: Database, bot: Bot, default_tz: str):
    kind = call.data[4:]
    if kind not in ("today", "tomorrow", "week") and not kind.lstrip("-").isdigit():
        await call.answer()
        return
    await call.answer("Рисую…")
    png = await build_image(db, call.from_user.id, await _user_tz(db, call.from_user.id, default_tz), kind)
    if png is None:
        await call.message.answer("Расписание пока пустое. Загрузи его: /schedule")
        return
    await bot.send_photo(call.message.chat.id, BufferedInputFile(png, filename=f"schedule-{kind}.png"))
