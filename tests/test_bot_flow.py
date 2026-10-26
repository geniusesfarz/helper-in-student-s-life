"""Прогон сценариев через настоящий Dispatcher с поддельной сессией Telegram."""
import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.methods import EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from bot.__main__ import reset_state_on_menu
from bot.db import Database
from bot.handlers.schedule import build_image
from bot.handlers import common, lectures, notes, schedule, subjects, tasks
from bot.keyboards import BTN_TODAY
from bot.reminders import check_once
from bot.timeutil import local_now

TZ = "Asia/Tashkent"
USER = User(id=42, is_bot=False, first_name="Фархад")
CHAT = Chat(id=42, type="private")


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent = []

    async def make_request(self, bot, method, timeout=None):
        self.sent.append(method)
        if isinstance(method, (SendMessage, EditMessageText)):
            return Message(message_id=len(self.sent), date=datetime.now(), chat=CHAT, text=method.text)
        return True

    async def stream_content(self, *a, **k):
        yield b""

    async def close(self):
        pass


class Harness:
    def __init__(self):
        self.session = FakeSession()
        self.bot = Bot("42:TEST", session=self.session, default=DefaultBotProperties(parse_mode="HTML"))
        self.db = Database(":memory:")
        self.n = 0

    async def setup(self):
        await self.db.connect()
        # роутеры — модульные синглтоны, поэтому на каждый тест свой Dispatcher с «отвязкой»
        for r in (common.router, schedule.router, tasks.router, notes.router, subjects.router, lectures.router):
            r._parent_router = None
        self.dp = Dispatcher(db=self.db, default_tz=TZ)
        self.dp.message.outer_middleware(reset_state_on_menu)
        self.dp.include_routers(common.router, schedule.router, tasks.router, notes.router, subjects.router, lectures.router)

    def texts(self):
        return [m.text for m in self.session.sent if isinstance(m, (SendMessage, EditMessageText))]

    async def send(self, text=None, **kw):
        self.n += 1
        msg = Message(message_id=self.n, date=datetime.now(), chat=CHAT, from_user=USER, text=text, **kw)
        await self.dp.feed_update(self.bot, Update(update_id=self.n, message=msg))
        return self.texts()[-1]

    async def press(self, data):
        self.n += 1
        msg = Message(message_id=1, date=datetime.now(), chat=CHAT, from_user=USER, text="x")
        cb = CallbackQuery(id=str(self.n), from_user=USER, chat_instance="c", message=msg, data=data)
        await self.dp.feed_update(self.bot, Update(update_id=self.n, callback_query=cb))
        return self.texts()[-1]





def test_full_flow():
    async def scenario():
        h = Harness()
        await h.setup()
        assert "Привет" in await h.send("/start")

        wd = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][local_now(TZ).weekday()]
        start = (local_now(TZ) + timedelta(minutes=10)).strftime("%H:%M")
        end = (local_now(TZ) + timedelta(minutes=11)).strftime("%H:%M")
        await h.send("/schedule")
        reply = await h.send(f"{wd} {start}-{end} Математика | ауд. 101")
        assert "Сохранил расписание: 1 пар" in reply
        if start < end:  # не переходим через полночь
            assert "Математика" in await h.send(BTN_TODAY)

        assert "Срок: завтра" in await h.send("/task Физика: лабораторная завтра 10:00")
        assert "лабораторная" in await h.send("/tasks")
        task_id = (await h.db.open_tasks(42))[0]["id"]
        assert "Задач нет" in await h.press(f"done:{task_id}")

        await h.send("/note")
        assert "сохранена в «Физика»" in await h.send("Физика: U = IR")
        subjects = await h.db.subjects(42)
        assert "U = IR" in await h.press(f"nsub:{subjects.index('Физика')}")

        # меню прерывает ввод задачи
        await h.send("/task")
        await h.send(BTN_TODAY)
        assert await h.db.open_tasks(42) == []

        await h.send("/remind 15")
        h.session.sent.clear()
        await check_once(h.bot, h.db)
        if start < end:
            assert any("Математика" in t for t in h.texts())
        # повторно не напоминает
        h.session.sent.clear()
        await check_once(h.bot, h.db)
        assert not any("Математика" in t for t in h.texts())

        # дедлайн через 30 минут
        await h.db.add_task(42, "сдать эссе", "", local_now(TZ) + timedelta(minutes=30))
        h.session.sent.clear()
        await check_once(h.bot, h.db)
        assert any("сдать эссе" in t and "осталось" in t for t in h.texts())
        await h.db.close()

    asyncio.run(scenario())


def test_lecture_upload():
    from aiogram.types import Document

    async def scenario():
        h = Harness()
        await h.setup()
        await h.send("/start")
        await h.send("/schedule")
        await h.send("Пн 09:00-10:30 Математика")
        doc = Document(file_id="F1", file_unique_id="U1", file_name="lec1.pdf")
        assert "Сохранил в «Математика»" in await h.send(document=doc, caption="Математика")
        doc2 = Document(file_id="F2", file_unique_id="U2", file_name="lec2.pdf")
        assert "К какому предмету" in await h.send(document=doc2)
        lec_id = 2
        assert "Сохранил в «Математика»" in await h.press(f"lset:{lec_id}:0")
        groups = await h.db.lecture_subjects(42)
        assert groups == [("Математика", 2)]
        await h.db.close()

    asyncio.run(scenario())


def test_create_subjects():
    from aiogram.types import Document

    async def scenario():
        h = Harness()
        await h.setup()
        await h.send("/start")
        assert "Предмет «Физика» готов" in await h.send("/subject Физика")
        assert "Предмет «Физика» готов" in await h.send("/subject физика")  # без дубля
        assert await h.db.subjects(42) == ["Физика"]

        doc = Document(file_id="F1", file_unique_id="U1", file_name="lec.pdf")
        assert "К какому предмету" in await h.send(document=doc)
        await h.press("subj_new:1")
        assert "сохранил туда лекцию" in await h.send("История Узбекистана")
        assert ("История Узбекистана", 1) in await h.db.lecture_subjects(42)

        await h.press("subj_new")
        assert "готов" in await h.send("Химия")
        assert "Химия" in await h.send("/subjects")
        await h.db.close()

    asyncio.run(scenario())


def test_ics_upload():
    from aiogram.types import Document

    from tests.test_parsing import ICS

    async def scenario():
        h = Harness()
        await h.setup()
        h.bot.download = lambda *_a, **_k: _bytes(ICS)
        await h.send("/start")
        await h.send("/schedule")
        doc = Document(file_id="I1", file_unique_id="I1", file_name="calendar.ics")
        assert "Сохранил расписание: 2 пар" in await h.send(document=doc)
        await h.db.close()

    asyncio.run(scenario())


async def _bytes(data):
    import io

    return io.BytesIO(data)


def test_schedule_image():
    from aiogram.methods import SendPhoto

    async def scenario():
        h = Harness()
        await h.setup()
        await h.send("/start")
        await h.send("/schedule")
        await h.send("Пн 09:00-10:30 Математика | 101\nВт 10:00-11:30 Физика")
        for kind in ("today", "week"):
            h.session.sent.clear()
            msg = Message(message_id=1, date=datetime.now(), chat=CHAT, from_user=USER, text="x")
            cb = CallbackQuery(id=kind, from_user=USER, chat_instance="c", message=msg, data=f"img:{kind}")
            await h.dp.feed_update(h.bot, Update(update_id=1000 + len(kind), callback_query=cb))
            assert any(isinstance(m, SendPhoto) for m in h.session.sent)
        png = await build_image(h.db, 42, TZ, "week")
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        await h.db.close()

    asyncio.run(scenario())
