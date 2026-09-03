"""Конфигурация бота: чтение окружения (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"


@dataclass
class Config:
    bot_token: str
    admin_user_id: int
    check_interval: int  # секунд
    check_size: int  # сколько объявлений брать за опрос
    max_send_per_check: int

    @property
    def data_dir(self) -> Path:
        return DATA_DIR


def load_config() -> Config:
    load_dotenv(ROOT_DIR / ".env")

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "Не задан BOT_TOKEN. Скопируйте .env.example в .env и укажите токен бота."
        )

    raw_user_id = os.getenv("ADMIN_USER_ID", "").strip()
    if not raw_user_id:
        raise RuntimeError(
            "Не задан ADMIN_USER_ID (ваш Telegram user id). Укажите его в .env"
        )

    return Config(
        bot_token=token,
        admin_user_id=int(raw_user_id),
        check_interval=_int_env("CHECK_INTERVAL", 60),
        check_size=_int_env("CHECK_SIZE", 50),
        max_send_per_check=_int_env("MAX_SEND_PER_CHECK", 15),
    )


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default