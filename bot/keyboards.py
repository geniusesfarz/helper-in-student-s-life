from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

BTN_TODAY = "📅 Сегодня"
BTN_TOMORROW = "📆 Завтра"
BTN_WEEK = "🗓 Неделя"
BTN_TASKS = "✅ Задачи"
BTN_NOTES = "📝 Заметки"
BTN_LECTURES = "📚 Лекции"
BTN_SCHEDULE = "⬆️ Загрузить расписание"
BTN_SETTINGS = "⚙️ Настройки"

MENU_BUTTONS = {BTN_TODAY, BTN_TOMORROW, BTN_WEEK, BTN_TASKS, BTN_NOTES, BTN_LECTURES, BTN_SCHEDULE, BTN_SETTINGS}

MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_TODAY), KeyboardButton(text=BTN_TOMORROW), KeyboardButton(text=BTN_WEEK)],
        [KeyboardButton(text=BTN_TASKS), KeyboardButton(text=BTN_NOTES), KeyboardButton(text=BTN_LECTURES)],
        [KeyboardButton(text=BTN_SCHEDULE), KeyboardButton(text=BTN_SETTINGS)],
    ],
    resize_keyboard=True,
)


def inline(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=d) for t, d in row] for row in rows]
    )


def subjects_keyboard(subjects: list[str], prefix: str, extra: list[tuple[str, str]] | None = None):
    rows = [[(s[:40], f"{prefix}:{i}")] for i, s in enumerate(subjects)]
    if extra:
        rows.append(extra)
    return inline(rows)
