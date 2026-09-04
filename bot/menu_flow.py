"""Механика «чистого» меню: удаляем нажатия кнопок и предыдущее служебное сообщение.

Reply-клавиатуру Telegram нельзя обновить через edit_message_text (API принимает
только InlineKeyboardMarkup), поэтому меню обновляется новым сообщением, а старое
служебное сообщение бота удаляется. Входящие нажатия кнопок тоже удаляются.
В итоге в чате остаётся только актуальное меню и содержательные сообщения.
"""
from __future__ import annotations

import logging

from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardMarkup

from bot import keyboards as kb

log = logging.getLogger(__name__)

MENU_MESSAGE_KEY = "bot_menu_message_id"


def is_button_press(text: str | None) -> bool:
    """Определяет, является ли сообщение пользователя нажатием reply-кнопки."""
    if not text:
        return False
    t = text.strip()
    return (
        t in (kb.BTN_SECTIONS, kb.BTN_ADD, kb.BTN_HELP, kb.BTN_CANCEL)
        or t.startswith("#")
        or t.startswith(kb.BTN_DELETE_PREFIX)
        or t.startswith(kb.BTN_PAUSE_PREFIX)
        or t.startswith(kb.BTN_RESUME_PREFIX)
    )


async def delete_press(message: Message) -> None:
    """Удаляет сообщение пользователя, если это нажатие кнопки."""
    if not is_button_press(message.text):
        return
    try:
        await message.delete()
    except Exception as exc:  # не критично, если не удалось
        log.debug("Не удалось удалить нажатие кнопки: %s", exc)


async def reset_state_keep_menu(state: FSMContext) -> None:
    """Сбрасывает FSM-состояние, сохраняя ссылку на актуальное меню-сообщение."""
    data = await state.get_data()
    menu_id = data.get(MENU_MESSAGE_KEY)
    await state.clear()
    if menu_id:
        await state.update_data(**{MENU_MESSAGE_KEY: menu_id})


async def render_menu(
    message: Message,
    state: FSMContext,
    text: str,
    keyboard: ReplyKeyboardMarkup,
    parse_mode: str | None = None,
) -> None:
    """Заменяет предыдущее служебное сообщение бота новым (с новой клавиатурой)."""
    data = await state.get_data()
    old_id = data.get(MENU_MESSAGE_KEY)
    if old_id:
        try:
            await message.bot.delete_message(message.chat.id, int(old_id))
        except Exception as exc:
            log.debug("Не удалось удалить прежнее меню: %s", exc)

    sent = await message.answer(text, reply_markup=keyboard, parse_mode=parse_mode)
    await state.update_data(**{MENU_MESSAGE_KEY: sent.message_id})