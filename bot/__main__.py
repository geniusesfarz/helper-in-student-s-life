import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from .config import load_config
from .db import Database
from .handlers import common, lectures, notes, schedule, tasks
from .keyboards import MENU_BUTTONS
from .reminders import reminder_loop


async def reset_state_on_menu(handler, event, data):
    """Кнопка меню или команда прерывают незаконченный ввод (задачи, расписания и т.п.)."""
    text = event.text or ""
    if text in MENU_BUTTONS or text.startswith("/"):
        state = data.get("state")
        if state is not None:
            await state.clear()
            data["raw_state"] = None
    return await handler(event, data)


COMMANDS = [
    BotCommand(command="today", description="Пары сегодня"),
    BotCommand(command="tomorrow", description="Пары завтра"),
    BotCommand(command="week", description="Расписание на неделю"),
    BotCommand(command="tasks", description="Задачи и дедлайны"),
    BotCommand(command="task", description="Добавить задачу"),
    BotCommand(command="notes", description="Заметки"),
    BotCommand(command="note", description="Добавить заметку"),
    BotCommand(command="lectures", description="Лекции по предметам"),
    BotCommand(command="schedule", description="Загрузить расписание"),
    BotCommand(command="settings", description="Настройки напоминаний"),
    BotCommand(command="help", description="Помощь"),
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config()
    db = Database(config.db_path)
    await db.connect()

    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(db=db, default_tz=config.default_tz)
    dp.message.outer_middleware(reset_state_on_menu)
    # common первым: /cancel и /start должны работать в любом состоянии
    dp.include_routers(common.router, schedule.router, tasks.router, notes.router, lectures.router)

    await bot.set_my_commands(COMMANDS)
    reminders = asyncio.create_task(reminder_loop(bot, db))
    try:
        await dp.start_polling(bot)
    finally:
        reminders.cancel()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
