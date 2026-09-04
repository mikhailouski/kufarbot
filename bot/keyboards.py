"""Reply-клавиатуры бота и тексты кнопок."""
from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from storage import WatchTarget

BTN_SECTIONS = "📋 Мои разделы"
BTN_ADD = "➕ Добавить раздел"
BTN_HELP = "ℹ️ Помощь"
BTN_CANCEL = "◀️ Отмена"
BTN_DELETE_PREFIX = "🗑 Удалить #"
BTN_PAUSE_PREFIX = "⏸ Пауза #"
BTN_RESUME_PREFIX = "▶️ Возобновить #"


def main_menu() -> ReplyKeyboardMarkup:
    """Главное меню бота."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_SECTIONS), KeyboardButton(text=BTN_ADD)],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
    )


def target_button(target: WatchTarget) -> str:
    """Текст кнопки раздела: '#12 label' (с пометкой паузы)."""
    status = "⏸ " if not target.enabled else ""
    return f"#{target.target_id} {status}{target.label}"


def targets_menu(targets: list[WatchTarget]) -> ReplyKeyboardMarkup:
    """Клавиатура со списком отслеживаемых разделов."""
    rows = [[KeyboardButton(text=target_button(t))] for t in targets]
    rows.append([KeyboardButton(text=BTN_CANCEL)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def target_actions_menu(target: WatchTarget) -> ReplyKeyboardMarkup:
    """Клавиатура действий над выбранным разделом."""
    toggle = BTN_RESUME_PREFIX if not target.enabled else BTN_PAUSE_PREFIX
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"{BTN_DELETE_PREFIX}{target.target_id}")],
            [KeyboardButton(text=f"{toggle}{target.target_id}")],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def wait_url_menu() -> ReplyKeyboardMarkup:
    """Клавиатура в режиме ожидания ссылки."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def parse_target_from_button(text: str) -> int | None:
    """Достаёт id раздела из текста кнопки.

    Поддерживает форматы: '#12 label' и '🗑 Удалить #12'.
    Возвращает None, если id извлечь не удалось.
    """
    text = text.strip()
    if not text.startswith("#"):
        idx = text.rfind("#")
        if idx == -1:
            return None
        text = text[idx:]
    try:
        return int(text[1:].split(maxsplit=1)[0])
    except (ValueError, IndexError):
        return None