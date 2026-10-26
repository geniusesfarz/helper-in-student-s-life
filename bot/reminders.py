"""Фоновая проверка: напоминания о парах и дедлайнах."""
import asyncio
import logging
from datetime import datetime, timedelta
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

from .db import Database
from .timeutil import local_now

log = logging.getLogger(__name__)
CHECK_INTERVAL = 30  # секунд


async def lesson_reminders(db: Database, user, now: datetime) -> list[str]:
    messages = []
    today = now.date().isoformat()
    for lesson in await db.lessons_for_day(user["id"], now.weekday()):
        start = datetime.combine(now.date(), datetime.strptime(lesson["start"], "%H:%M").time())
        if not (start - timedelta(minutes=user["remind_before"]) <= now < start):
            continue
        if await db.lesson_reminder_sent(lesson["id"], today):
            continue
        await db.mark_lesson_reminder(lesson["id"], today)
        minutes = int((start - now).total_seconds() // 60)
        place = f"\n📍 {escape(lesson['room'])}" if lesson["room"] else ""
        teacher = f"\n👤 {escape(lesson['teacher'])}" if lesson["teacher"] else ""
        messages.append(
            f"🔔 Через {minutes} мин: <b>{escape(lesson['subject'])}</b> ({lesson['start']}–{lesson['end']})"
            f"{place}{teacher}"
        )
    return messages


async def task_reminders(db: Database, user, now: datetime) -> list[str]:
    messages = []
    for task in await db.tasks_with_due(user["id"]):
        due = datetime.fromisoformat(task["due"])
        left = due - now
        subj = f"[{escape(task['subject'])}] " if task["subject"] else ""
        if left <= timedelta(hours=1) and not task["reminded_hour"]:
            await db.mark_task_reminded(task["id"], "reminded_hour")
            await db.mark_task_reminded(task["id"], "reminded_day")
            when = "дедлайн уже наступил" if left <= timedelta(0) else f"осталось {int(left.total_seconds() // 60)} мин"
            messages.append(f"⏰ {subj}{escape(task['text'])}: {when}!")
        elif timedelta(hours=1) < left <= timedelta(days=1) and not task["reminded_day"]:
            await db.mark_task_reminded(task["id"], "reminded_day")
            messages.append(f"📌 Завтра или раньше дедлайн: {subj}{escape(task['text'])} (до {due.strftime('%d.%m %H:%M')})")
    return messages


async def check_once(bot: Bot, db: Database) -> None:
    for user in await db.all_users():
        try:
            now = local_now(user["tz"])
            for text in await lesson_reminders(db, user, now) + await task_reminders(db, user, now):
                await bot.send_message(user["id"], text)
        except TelegramForbiddenError:
            await db.update_user(user["id"], reminders_on=0)  # пользователь заблокировал бота
        except Exception:
            log.exception("Ошибка напоминаний для пользователя %s", user["id"])


async def reminder_loop(bot: Bot, db: Database) -> None:
    while True:
        await check_once(bot, db)
        await asyncio.sleep(CHECK_INTERVAL)
