from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ..db import Database
from ..keyboards import inline

router = Router()

ASK_NAME = "Напиши название предмета, например: <code>Математический анализ</code>"


class NewSubject(StatesGroup):
    waiting = State()


def _clean(name: str) -> str | None:
    name = " ".join(name.split()).strip(" :")
    return name if 0 < len(name) <= 60 else None


async def _create(message: Message, db: Database, name: str, default_tz: str, lecture_id: int | None = None):
    clean = _clean(name)
    if not clean:
        await message.answer("Название должно быть от 1 до 60 символов. " + ASK_NAME)
        return False
    await db.ensure_user(message.from_user.id, default_tz)
    subject = await db.add_subject(message.from_user.id, clean)
    if lecture_id is not None:
        await db.set_lecture_subject(message.from_user.id, lecture_id, subject)
        await message.answer(f"Создал предмет «{escape(subject)}» и сохранил туда лекцию 📚")
    else:
        await message.answer(
            f"Предмет «{escape(subject)}» готов ✅\n"
            "Чтобы сохранить туда лекцию, пришли файл или фото и выбери этот предмет."
        )
    return True


@router.message(Command("subject"))
async def subject_cmd(message: Message, command: CommandObject, db: Database, state: FSMContext, default_tz: str):
    if command.args:
        await _create(message, db, command.args, default_tz)
    else:
        await state.set_state(NewSubject.waiting)
        await message.answer(ASK_NAME)


@router.callback_query(F.data.startswith("subj_new"))
async def subject_new_cb(call: CallbackQuery, state: FSMContext):
    _, _, lecture_id = call.data.partition(":")
    await state.set_state(NewSubject.waiting)
    await state.update_data(lecture_id=int(lecture_id) if lecture_id else None)
    await call.message.answer(ASK_NAME)
    await call.answer()


@router.message(StateFilter(NewSubject.waiting), F.text)
async def subject_name(message: Message, db: Database, state: FSMContext, default_tz: str):
    data = await state.get_data()
    if await _create(message, db, message.text, default_tz, data.get("lecture_id")):
        await state.clear()


@router.message(Command("subjects"))
async def subjects_list(message: Message, db: Database, default_tz: str):
    await db.ensure_user(message.from_user.id, default_tz)
    subjects = await db.subjects(message.from_user.id)
    text = "<b>Предметы</b>\n" + "\n".join(f"• {escape(s)}" for s in subjects) if subjects else "Предметов пока нет."
    await message.answer(text, reply_markup=inline([[("➕ Новый предмет", "subj_new")]]))
