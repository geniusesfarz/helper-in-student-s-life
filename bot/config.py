import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Простая загрузка .env без лишних зависимостей."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Config:
    bot_token: str
    default_tz: str
    db_path: str


def load_config() -> Config:
    _load_dotenv()
    token = os.environ.get("BOT_TOKEN", "")
    if not token:
        raise RuntimeError("Не задан BOT_TOKEN. Скопируйте .env.example в .env и впишите токен.")
    return Config(
        bot_token=token,
        default_tz=os.environ.get("DEFAULT_TZ", "Asia/Tashkent"),
        db_path=os.environ.get("DB_PATH", "data/bot.db"),
    )
