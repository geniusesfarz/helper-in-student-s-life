from datetime import datetime
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ..db import Database
from ..keyboards import BTN_TASKS, inline
from ..text_utils import format_due, parse_due, split_subject
from ..timeutil import local_now

router = Router()

TASK_HINT = (
    "Напиши задачу. Предмет и срок необязательны:\n"
    "<code>Математика: решить №5–10 до 30.10 18:00</code>\n"
    "<code>Эссе по истории завтра</code>\n"
    "<code>Купить тетради</code>"
)


class AddTask(StatesGroup):
    waiting = State()


async def _tz(db: Database, user_id: int, default_tz: str) -> str:
    await db.ensure_user(user_id, default_tz)
    return (await db.get_user(user_id))["tz"]


async def _add(message: Message, db: Database, text: str, default_tz: str):
    now = local_now(await _tz(db, message.from_user.id, default_tz))
    subject, rest = split_subject(text)
    body, due = parse_due(rest, now)
    if not body:
        await message.answer("Пустая задача. " + TASK_HINT)
        return
    await db.add_task(message.from_user.id, body, subject, due)
    when = f"\nСрок: {format_due(due, now)}. Напомню за сутки и за час." if due else ""
    prefix = f"[{escape(subject)}] " if subject else ""
    await message.answer(f"Добавил задачу: {prefix}{escape(body)}{when}")


async def _list_view(db: Database, user_id: int, default_tz: str):
    now = local_now(await _tz(db, user_id, default_tz))
    tasks = await db.open_tasks(user_id)
    if not tasks:
        return "Задач нет 🎉", inline([[("➕ Добавить задачу", "task_add")]])
    lines, buttons = [], []
    for i, t in enumerate(tasks, 1):
        subj = f"[{escape(t['subject'])}] " if t["subject"] else ""
        due = f" — <i>{format_due(datetime.fromisoformat(t['due']), now)}</i>" if t["due"] else ""
        lines.append(f"{i}. {subj}{escape(t['text'])}{due}")
        buttons.append((f"✅ {i}", f"done:{t['id']}"))
    rows = [buttons[i:i + 5] for i in range(0, len(buttons), 5)]
    rows.append([("➕ Добавить задачу", "task_add")])
    return "<b>Задачи</b>\n" + "\n".join(lines) + "\n\nНажми ✅ с номером, когда сделаешь.", inline(rows)


@router.message(Command("task"))
async def task_cmd(message: Message, command: CommandObject, db: Database, state: FSMContext, default_tz: str):
    if command.args:
        await _add(message, db, command.args, default_tz)
    else:
        await state.set_state(AddTask.waiting)
        await message.answer(TASK_HINT)


@router.callback_query(F.data == "task_add")
async def task_add_cb(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddTask.waiting)
    await call.message.answer(TASK_HINT)
    await call.answer()


@router.message(StateFilter(AddTask.waiting), F.text)
async def task_text(message: Message, db: Database, state: FSMContext, default_tz: str):
    await state.clear()
    await _add(message, db, message.text, default_tz)


@router.message(Command("tasks"))
@router.message(F.text == BTN_TASKS)
async def tasks_list(message: Message, db: Database, default_tz: str):
    text, kb = await _list_view(db, message.from_user.id, default_tz)
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("done:"))
async def done_cb(call: CallbackQuery, db: Database, default_tz: str):
    await db.set_task_done(call.from_user.id, int(call.data[5:]))
    text, kb = await _list_view(db, call.from_user.id, default_tz)
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer("Отлично! 💪")
