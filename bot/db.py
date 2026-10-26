from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from .schedule_parser import Lesson

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    tz TEXT NOT NULL,
    remind_before INTEGER NOT NULL DEFAULT 15,
    reminders_on INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    weekday INTEGER NOT NULL,
    start TEXT NOT NULL,
    end TEXT NOT NULL,
    subject TEXT NOT NULL,
    room TEXT NOT NULL DEFAULT '',
    teacher TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL,
    due TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    reminded_day INTEGER NOT NULL DEFAULT 0,
    reminded_hour INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lectures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    subject TEXT NOT NULL DEFAULT '',
    file_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS subjects (
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    PRIMARY KEY (user_id, name)
);
CREATE TABLE IF NOT EXISTS sent_lesson_reminders (
    lesson_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    PRIMARY KEY (lesson_id, date)
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    # --- пользователи ---
    async def ensure_user(self, user_id: int, tz: str) -> None:
        await self.conn.execute("INSERT OR IGNORE INTO users (id, tz) VALUES (?, ?)", (user_id, tz))
        await self.conn.commit()

    async def get_user(self, user_id: int):
        cur = await self.conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return await cur.fetchone()

    async def all_users(self):
        cur = await self.conn.execute("SELECT * FROM users WHERE reminders_on = 1")
        return await cur.fetchall()

    async def update_user(self, user_id: int, **fields) -> None:
        cols = ", ".join(f"{k} = ?" for k in fields)
        await self.conn.execute(f"UPDATE users SET {cols} WHERE id = ?", (*fields.values(), user_id))
        await self.conn.commit()

    # --- расписание ---
    async def replace_schedule(self, user_id: int, lessons: list[Lesson]) -> None:
        await self.conn.execute("DELETE FROM lessons WHERE user_id = ?", (user_id,))
        await self.conn.executemany(
            "INSERT INTO lessons (user_id, weekday, start, end, subject, room, teacher) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(user_id, l.weekday, l.start.strftime("%H:%M"), l.end.strftime("%H:%M"), l.subject, l.room, l.teacher)
             for l in lessons],
        )
        await self.conn.commit()

    async def lessons_for_day(self, user_id: int, weekday: int):
        cur = await self.conn.execute(
            "SELECT * FROM lessons WHERE user_id = ? AND weekday = ? ORDER BY start", (user_id, weekday)
        )
        return await cur.fetchall()

    async def all_lessons(self, user_id: int):
        cur = await self.conn.execute(
            "SELECT * FROM lessons WHERE user_id = ? ORDER BY weekday, start", (user_id,)
        )
        return await cur.fetchall()

    async def subjects(self, user_id: int) -> list[str]:
        cur = await self.conn.execute(
            "SELECT name FROM subjects WHERE user_id = ? "
            "UNION SELECT DISTINCT subject FROM lessons WHERE user_id = ? "
            "UNION SELECT DISTINCT subject FROM notes WHERE user_id = ? AND subject != '' "
            "UNION SELECT DISTINCT subject FROM lectures WHERE user_id = ? AND subject != '' "
            "ORDER BY 1",
            (user_id, user_id, user_id, user_id),
        )
        return [r[0] for r in await cur.fetchall()]

    async def add_subject(self, user_id: int, name: str) -> str:
        """Создаёт предмет; если такой уже есть (без учёта регистра), возвращает существующее название."""
        for existing in await self.subjects(user_id):
            if existing.lower() == name.lower():
                return existing
        await self.conn.execute("INSERT INTO subjects (user_id, name) VALUES (?, ?)", (user_id, name))
        await self.conn.commit()
        return name

    async def lesson_reminder_sent(self, lesson_id: int, date: str) -> bool:
        cur = await self.conn.execute(
            "SELECT 1 FROM sent_lesson_reminders WHERE lesson_id = ? AND date = ?", (lesson_id, date)
        )
        return await cur.fetchone() is not None

    async def mark_lesson_reminder(self, lesson_id: int, date: str) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO sent_lesson_reminders (lesson_id, date) VALUES (?, ?)", (lesson_id, date)
        )
        await self.conn.commit()

    # --- задачи ---
    async def add_task(self, user_id: int, text: str, subject: str = "", due: datetime | None = None) -> int:
        cur = await self.conn.execute(
            "INSERT INTO tasks (user_id, subject, text, due) VALUES (?, ?, ?, ?)",
            (user_id, subject, text, due.isoformat(timespec="minutes") if due else None),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def open_tasks(self, user_id: int):
        cur = await self.conn.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND done = 0 ORDER BY due IS NULL, due, id", (user_id,)
        )
        return await cur.fetchall()

    async def tasks_with_due(self, user_id: int):
        cur = await self.conn.execute(
            "SELECT * FROM tasks WHERE user_id = ? AND done = 0 AND due IS NOT NULL", (user_id,)
        )
        return await cur.fetchall()

    async def set_task_done(self, user_id: int, task_id: int) -> bool:
        cur = await self.conn.execute(
            "UPDATE tasks SET done = 1 WHERE id = ? AND user_id = ?", (task_id, user_id)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def mark_task_reminded(self, task_id: int, field: str) -> None:
        assert field in ("reminded_day", "reminded_hour")
        await self.conn.execute(f"UPDATE tasks SET {field} = 1 WHERE id = ?", (task_id,))
        await self.conn.commit()

    # --- заметки ---
    async def add_note(self, user_id: int, text: str, subject: str = "") -> None:
        await self.conn.execute(
            "INSERT INTO notes (user_id, subject, text, created) VALUES (?, ?, ?, ?)",
            (user_id, subject, text, datetime.now(timezone.utc).isoformat(timespec="minutes")),
        )
        await self.conn.commit()

    async def notes(self, user_id: int, subject: str | None = None):
        if subject is None:
            cur = await self.conn.execute(
                "SELECT * FROM notes WHERE user_id = ? ORDER BY id DESC LIMIT 30", (user_id,)
            )
        else:
            cur = await self.conn.execute(
                "SELECT * FROM notes WHERE user_id = ? AND subject = ? ORDER BY id DESC", (user_id, subject)
            )
        return await cur.fetchall()

    async def delete_note(self, user_id: int, note_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
        await self.conn.commit()
        return cur.rowcount > 0

    # --- лекции ---
    async def add_lecture(self, user_id: int, file_id: str, kind: str, title: str, subject: str = "") -> int:
        cur = await self.conn.execute(
            "INSERT INTO lectures (user_id, subject, file_id, kind, title, created) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, subject, file_id, kind, title, datetime.now(timezone.utc).isoformat(timespec="minutes")),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def set_lecture_subject(self, user_id: int, lecture_id: int, subject: str) -> None:
        await self.conn.execute(
            "UPDATE lectures SET subject = ? WHERE id = ? AND user_id = ?", (subject, lecture_id, user_id)
        )
        await self.conn.commit()

    async def lectures(self, user_id: int, subject: str):
        cur = await self.conn.execute(
            "SELECT * FROM lectures WHERE user_id = ? AND subject = ? ORDER BY id", (user_id, subject)
        )
        return await cur.fetchall()

    async def lecture_subjects(self, user_id: int) -> list[tuple[str, int]]:
        cur = await self.conn.execute(
            "SELECT subject, COUNT(*) FROM lectures WHERE user_id = ? GROUP BY subject ORDER BY subject",
            (user_id,),
        )
        return [(r[0], r[1]) for r in await cur.fetchall()]
