"""Расписание картинкой: вертикальная карточка под экран телефона."""
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).parent / "assets" / "fonts"
WIDTH = 1080
PAD = 56
CARD_H = 150
CARD_GAP = 18
DAY_GAP = 44

# палитра согласована с макетом интерфейса бота
BG = "#F3F4F7"
CARD = "#FFFFFF"
TEXT = "#15171A"
MUTED = "#5F6368"
ACCENT = "#2F6FEB"
TODAY_BG = "#E6EEFD"
RADIUS = 32  # ~16px на экране телефона при ширине картинки 1080
# приглушённые пастельные цвета полоски предмета; текст всегда тёмный, контраст не страдает
PALETTE = ["#A8C5FA", "#A7E0C9", "#F9C9A0", "#D6B8F0", "#F5B5C8",
           "#9FD8E8", "#C7DFA0", "#F7DC8F", "#B9C2F2", "#E8C3A8"]


@dataclass
class DayBlock:
    title: str
    lessons: list  # строки из таблицы lessons
    highlight: bool = False
    current_lesson_id: int | None = None  # пара, которая идёт прямо сейчас


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")), size)


def _fit(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def _day_height(day: DayBlock) -> int:
    rows = max(len(day.lessons), 1)
    return 70 + rows * (CARD_H + CARD_GAP)


def render_schedule(title: str, days: list[DayBlock], subjects: list[str]) -> bytes:
    colors = {s: PALETTE[i % len(PALETTE)] for i, s in enumerate(subjects)}
    height = PAD + 110 + sum(_day_height(d) + DAY_GAP for d in days) + PAD - DAY_GAP
    img = Image.new("RGB", (WIDTH, height), BG)
    draw = ImageDraw.Draw(img)

    f_title, f_day = _font(60, True), _font(40, True)
    f_time, f_subj, f_meta, f_empty = _font(34, True), _font(38, True), _font(30), _font(34)

    y = PAD
    draw.text((PAD, y), title, font=f_title, fill=TEXT)
    y += 110

    for day in days:
        block_h = _day_height(day)
        if day.highlight:
            draw.rounded_rectangle((PAD - 24, y - 16, WIDTH - PAD + 24, y + block_h - 4), RADIUS, fill=TODAY_BG)
        draw.text((PAD, y), day.title, font=f_day, fill=ACCENT if day.highlight else TEXT)
        y += 70
        if not day.lessons:
            draw.rounded_rectangle((PAD, y, WIDTH - PAD, y + CARD_H), RADIUS, fill=CARD)
            draw.text((PAD + 36, y + CARD_H // 2), "Пар нет", font=f_empty, fill=MUTED, anchor="lm")
            y += CARD_H + CARD_GAP
        for lesson in day.lessons:
            color = colors.get(lesson["subject"], PALETTE[0])
            is_now = lesson["id"] == day.current_lesson_id
            draw.rounded_rectangle((PAD, y, WIDTH - PAD, y + CARD_H), RADIUS, fill=CARD,
                                   outline=ACCENT if is_now else None, width=5 if is_now else 0)
            draw.rounded_rectangle((PAD + 18, y + 22, PAD + 30, y + CARD_H - 22), 6, fill=color)
            x_time, x_body = PAD + 60, PAD + 260
            draw.text((x_time, y + 34), lesson["start"], font=f_time, fill=TEXT)
            draw.text((x_time, y + 82), lesson["end"], font=f_meta, fill=MUTED)
            body_w = WIDTH - PAD - 30 - x_body
            draw.text((x_body, y + 30), _fit(draw, lesson["subject"], f_subj, body_w), font=f_subj, fill=TEXT)
            meta = " · ".join(x for x in (lesson["room"], lesson["teacher"]) if x)
            if meta:
                draw.text((x_body, y + 84), _fit(draw, meta, f_meta, body_w), font=f_meta, fill=MUTED)
            y += CARD_H + CARD_GAP
        y += DAY_GAP - CARD_GAP + 18

    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
