from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..db import Database
from ..keyboards import BTN_SETTINGS, MAIN_MENU, inline
from ..timeutil import valid_tz

router = Router()

HELP = (
    "Я помогаю с учёбой: расписание, напоминания о парах и дедлайнах, задачи, заметки и лекции.\n\n"
    "<b>С чего начать</b>\n"
    "1. Нажми «⬆️ Загрузить расписание» и пришли расписание текстом или файлом (.ics, Excel, CSV).\n"
    "2. Я буду напоминать о каждой паре за 15 минут (меняется в «⚙️ Настройки»).\n\n"
    "<b>Команды</b>\n"
    "/today, /tomorrow, /week — расписание\n"
    "/task Математика: решить №5 до 30.10 18:00 — задача с дедлайном\n"
    "/tasks — список задач\n"
    "/note Физика: формула Ома U = IR — заметка\n"
    "/notes — заметки\n"
    "/lectures — лекции по предметам (чтобы сохранить лекцию, просто пришли файл, фото или голосовое)\n"
    "/subject Математика — создать предмет, /subjects — список предметов\n"
    "/remind 10 — напоминать за 10 минут до пары\n"
    "/tz Europe/Moscow — часовой пояс\n"
    "/cancel — отменить текущее действие"
)

REMIND_OPTIONS = [5, 10, 15, 30, 60]


@router.message(CommandStart())
async def start(message: Message, db: Database, default_tz: str, state: FSMContext):
    await state.clear()
    await db.ensure_user(message.from_user.id, default_tz)
    await message.answer(f"Привет, {message.from_user.first_name}! 👋\n\n{HELP}", reply_markup=MAIN_MENU)


@router.message(Command("help"))
async def help_(message: Message):
    await message.answer(HELP, reply_markup=MAIN_MENU)


@router.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменил.", reply_markup=MAIN_MENU)


def _settings_view(user) -> tuple[str, object]:
    status = "включены" if user["reminders_on"] else "выключены"
    text = (
        "<b>Настройки</b>\n"
        f"Напоминания: {status}\n"
        f"Напоминать до пары за: {user['remind_before']} мин\n"
        f"Часовой пояс: {user['tz']} (сменить: /tz Europe/Moscow)"
    )
    rows = [[(("• " if m == user["remind_before"] else "") + f"{m} мин", f"rb:{m}") for m in REMIND_OPTIONS]]
    rows.append([("🔕 Выключить напоминания" if user["reminders_on"] else "🔔 Включить напоминания", "rtoggle")])
    return text, inline(rows)


@router.message(Command("settings"))
@router.message(F.text == BTN_SETTINGS)
async def settings(message: Message, db: Database, default_tz: str):
    await db.ensure_user(message.from_user.id, default_tz)
    text, kb = _settings_view(await db.get_user(message.from_user.id))
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("rb:"))
async def set_remind_cb(call: CallbackQuery, db: Database):
    await db.update_user(call.from_user.id, remind_before=int(call.data[3:]))
    text, kb = _settings_view(await db.get_user(call.from_user.id))
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer("Сохранено")


@router.callback_query(F.data == "rtoggle")
async def toggle_cb(call: CallbackQuery, db: Database):
    user = await db.get_user(call.from_user.id)
    await db.update_user(call.from_user.id, reminders_on=0 if user["reminders_on"] else 1)
    text, kb = _settings_view(await db.get_user(call.from_user.id))
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@router.message(Command("remind"))
async def remind_cmd(message: Message, command: CommandObject, db: Database, default_tz: str):
    await db.ensure_user(message.from_user.id, default_tz)
    arg = (command.args or "").strip()
    if not arg.isdigit() or not 0 < int(arg) <= 180:
        await message.answer("Напиши число минут от 1 до 180, например: /remind 10")
        return
    await db.update_user(message.from_user.id, remind_before=int(arg))
    await message.answer(f"Готово, напомню за {arg} мин до пары.")


@router.message(Command("tz"))
async def tz_cmd(message: Message, command: CommandObject, db: Database, default_tz: str):
    await db.ensure_user(message.from_user.id, default_tz)
    arg = (command.args or "").strip()
    if not arg or not valid_tz(arg):
        await message.answer(
            "Укажи часовой пояс в формате Регион/Город, например:\n"
            "/tz Asia/Tashkent\n/tz Europe/Moscow\n/tz Asia/Almaty"
        )
        return
    await db.update_user(message.from_user.id, tz=arg)
    await message.answer(f"Часовой пояс: {arg}")
