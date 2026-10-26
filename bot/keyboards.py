from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

BTN_TODAY = "Сегодня"
BTN_TOMORROW = "Завтра"
BTN_WEEK = "Неделя"
BTN_TASKS = "Задачи"
BTN_NOTES = "Заметки"
BTN_LECTURES = "Лекции"
BTN_SCHEDULE = "Загрузить расписание"
BTN_SETTINGS = "Настройки"
BTN_MORE = "Ещё…"
BTN_BACK = "‹ Назад"

# Подписи кнопок из старого меню: у кого оно ещё открыто, кнопки продолжают работать.
LEGACY_BUTTONS = {
    "📅 Сегодня": BTN_TODAY,
    "📆 Завтра": BTN_TOMORROW,
    "🗓 Неделя": BTN_WEEK,
    "✅ Задачи": BTN_TASKS,
    "📝 Заметки": BTN_NOTES,
    "📚 Лекции": BTN_LECTURES,
    "⬆️ Загрузить расписание": BTN_SCHEDULE,
    "⚙️ Настройки": BTN_SETTINGS,
}

MENU_BUTTONS = {
    BTN_TODAY, BTN_TOMORROW, BTN_WEEK, BTN_TASKS, BTN_NOTES, BTN_LECTURES,
    BTN_SCHEDULE, BTN_SETTINGS, BTN_MORE, BTN_BACK,
}


def _reply(rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True,
    )


MAIN_MENU = _reply([[BTN_TODAY, BTN_WEEK], [BTN_TASKS, BTN_MORE]])
MORE_MENU = _reply([[BTN_TOMORROW, BTN_NOTES], [BTN_LECTURES, BTN_SETTINGS], [BTN_SCHEDULE], [BTN_BACK]])


def inline(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows]
    )


def subjects_keyboard(subjects: list[str], prefix: str, extra: list[tuple[str, str]] | None = None):
    rows = [[(s[:40], f"{prefix}:{i}")] for i, s in enumerate(subjects)]
    if extra:
        rows.append(extra)
    return inline(rows)
