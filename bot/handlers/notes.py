from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ..db import Database
from ..keyboards import BTN_NOTES, inline, subjects_keyboard
from ..text_utils import split_subject

router = Router()

NOTE_HINT = (
    "Напиши заметку. Чтобы привязать к предмету, начни с его названия и двоеточия:\n"
    "<code>Физика: закон Ома U = IR</code>"
)


class AddNote(StatesGroup):
    waiting = State()


async def _add(message: Message, db: Database, text: str, default_tz: str):
    await db.ensure_user(message.from_user.id, default_tz)
    subject, body = split_subject(text)
    await db.add_note(message.from_user.id, body, subject)
    where = f" в «{escape(subject)}»" if subject else ""
    await message.answer(f"Заметка сохранена{where} 📝")


@router.message(Command("note"))
async def note_cmd(message: Message, command: CommandObject, db: Database, state: FSMContext, default_tz: str):
    if command.args:
        await _add(message, db, command.args, default_tz)
    else:
        await state.set_state(AddNote.waiting)
        await message.answer(NOTE_HINT)


@router.callback_query(F.data == "note_add")
async def note_add_cb(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddNote.waiting)
    await call.message.answer(NOTE_HINT)
    await call.answer()


@router.message(StateFilter(AddNote.waiting), F.text)
async def note_text(message: Message, db: Database, state: FSMContext, default_tz: str):
    await state.clear()
    await _add(message, db, message.text, default_tz)


@router.message(Command("notes"))
@router.message(F.text == BTN_NOTES)
async def notes_menu(message: Message, db: Database, default_tz: str):
    await db.ensure_user(message.from_user.id, default_tz)
    subjects = await db.subjects(message.from_user.id)
    kb = subjects_keyboard(
        subjects, "nsub", extra=[("🕘 Последние", "nlast"), ("➕ Новая заметка", "note_add")]
    )
    kb.inline_keyboard.append(inline([[("📁 Новый предмет", "subj_new")]]).inline_keyboard[0])
    await message.answer("<b>Заметки</b>\nВыбери предмет:", reply_markup=kb)


def _render(notes, title: str) -> str:
    if not notes:
        return f"<b>{escape(title)}</b>\nЗаметок пока нет."
    lines = []
    for n in notes:
        subj = f"<i>{escape(n['subject'])}</i> · " if n["subject"] and title == "Последние заметки" else ""
        lines.append(f"• {subj}{escape(n['text'])}  /del_{n['id']}")
    text = f"<b>{escape(title)}</b>\n" + "\n".join(lines)
    return text[:4000]


@router.callback_query(F.data.startswith("nsub:"))
async def notes_by_subject(call: CallbackQuery, db: Database):
    subjects = await db.subjects(call.from_user.id)
    idx = int(call.data[5:])
    if idx >= len(subjects):
        await call.answer("Список предметов изменился, открой заметки заново.")
        return
    subject = subjects[idx]
    await call.message.answer(
        _render(await db.notes(call.from_user.id, subject), subject),
        reply_markup=inline([[("➕ Новая заметка", "note_add")]]),
    )
    await call.answer()


@router.callback_query(F.data == "nlast")
async def notes_last(call: CallbackQuery, db: Database):
    await call.message.answer(_render(await db.notes(call.from_user.id), "Последние заметки"))
    await call.answer()


@router.message(F.text.regexp(r"^/del_(\d+)"))
async def delete_note(message: Message, db: Database):
    note_id = int(message.text.split("_", 1)[1].split("@")[0])
    ok = await db.delete_note(message.from_user.id, note_id)
    await message.answer("Заметка удалена." if ok else "Такой заметки нет.")
