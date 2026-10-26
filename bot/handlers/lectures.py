from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.types import CallbackQuery, Message

from ..db import Database
from ..keyboards import BTN_LECTURES, inline, subjects_keyboard
from ..text_utils import split_subject

router = Router()

NO_SUBJECT = "Без предмета"


def _extract_file(message: Message) -> tuple[str, str, str] | None:
    """Возвращает (file_id, тип, название) для поддерживаемых вложений."""
    if message.document:
        return message.document.file_id, "document", message.document.file_name or "Файл"
    if message.photo:
        return message.photo[-1].file_id, "photo", "Фото"
    if message.voice:
        return message.voice.file_id, "voice", "Голосовое"
    if message.audio:
        return message.audio.file_id, "audio", message.audio.file_name or message.audio.title or "Аудио"
    if message.video:
        return message.video.file_id, "video", message.video.file_name or "Видео"
    if message.video_note:
        return message.video_note.file_id, "video_note", "Видеосообщение"
    return None


def _match_subject(caption: str, subjects: list[str]) -> tuple[str, str]:
    """Определяет предмет по подписи. Возвращает (предмет, название)."""
    subject, rest = split_subject(caption)
    if subject:
        return subject, rest
    first = caption.splitlines()[0].strip().lower()
    for s in subjects:
        if first == s.lower() or first.startswith(s.lower() + " "):
            return s, caption
    return "", caption


@router.message(StateFilter(None), F.document | F.photo | F.voice | F.audio | F.video | F.video_note)
async def save_lecture(message: Message, db: Database, default_tz: str):
    await db.ensure_user(message.from_user.id, default_tz)
    file_id, kind, title = _extract_file(message)
    subjects = await db.subjects(message.from_user.id)
    subject = ""
    if message.caption:
        subject, caption_title = _match_subject(message.caption, subjects)
        title = caption_title or title
    lecture_id = await db.add_lecture(message.from_user.id, file_id, kind, title, subject)
    if subject:
        await message.reply(f"Сохранил в «{escape(subject)}» 📚")
        return
    kb = subjects_keyboard(
        subjects,
        f"lset:{lecture_id}",
        extra=[("✏️ Новый предмет", f"subj_new:{lecture_id}"), (NO_SUBJECT, f"lset:{lecture_id}:-1")],
    )
    await message.reply("К какому предмету отнести?", reply_markup=kb)


@router.callback_query(F.data.startswith("lset:"))
async def set_subject(call: CallbackQuery, db: Database):
    _, lecture_id, idx = call.data.split(":")
    idx = int(idx)
    subjects = await db.subjects(call.from_user.id)
    subject = subjects[idx] if 0 <= idx < len(subjects) else NO_SUBJECT
    await db.set_lecture_subject(call.from_user.id, int(lecture_id), subject)
    await call.message.edit_text(f"Сохранил в «{escape(subject)}» 📚")
    await call.answer()


@router.message(Command("lectures"))
@router.message(F.text == BTN_LECTURES)
async def lectures_menu(message: Message, db: Database, default_tz: str):
    await db.ensure_user(message.from_user.id, default_tz)
    groups = await db.lecture_subjects(message.from_user.id)
    if not groups:
        await message.answer(
            "Лекций пока нет. Просто пришли мне файл, фото конспекта или голосовое, "
            "а я спрошу, к какому предмету его отнести.\n"
            "Предмет можно создать заранее кнопкой ниже.",
            reply_markup=inline([[("➕ Новый предмет", "subj_new")]]),
        )
        return
    kb = subjects_keyboard(
        [f"{s or NO_SUBJECT} ({n})" for s, n in groups], "lsub", extra=[("➕ Новый предмет", "subj_new")]
    )
    await message.answer("<b>Лекции</b>\nВыбери предмет:", reply_markup=kb)


@router.callback_query(F.data.startswith("lsub:"))
async def lectures_by_subject(call: CallbackQuery, db: Database, bot: Bot):
    groups = await db.lecture_subjects(call.from_user.id)
    idx = int(call.data[5:])
    if idx >= len(groups):
        await call.answer("Список изменился, открой лекции заново.")
        return
    subject = groups[idx][0]
    await call.answer()
    await call.message.answer(f"<b>{escape(subject or NO_SUBJECT)}</b>")
    chat_id = call.message.chat.id
    for lec in await db.lectures(call.from_user.id, subject):
        caption = escape(lec["title"])[:1000]
        send = {
            "document": bot.send_document,
            "photo": bot.send_photo,
            "voice": bot.send_voice,
            "audio": bot.send_audio,
            "video": bot.send_video,
        }.get(lec["kind"])
        if send:
            await send(chat_id, lec["file_id"], caption=caption)
        else:
            await bot.send_video_note(chat_id, lec["file_id"])
