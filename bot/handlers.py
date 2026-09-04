"""Обработчики команд Telegram-бота."""
from __future__ import annotations

import logging

from aiogram import Dispatcher, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot import keyboards as kb
from bot.buttons import AddStates, setup_button_handlers
from bot.context import BotContext  # noqa: F401 (реэкспорт для main.py)
from bot import menu_flow
from bot.menu_flow import render_menu, reset_state_keep_menu
from bot.notifier import format_error, format_watch_list
from bot.watch_service import is_admin, watch_url

log = logging.getLogger(__name__)


def setup_handlers(dp: Dispatcher, ctx: "BotContext") -> None:
    """Регистрирует команды и кнопки бота."""
    router = Router()

    @router.message(CommandStart())
    async def on_start(message: Message, state: FSMContext) -> None:
        if not is_admin(message.from_user.id if message.from_user else None, ctx):
            await message.answer("⛔ У вас нет доступа к этому боту.")
            return
        await reset_state_keep_menu(state)
        # удалим прежнее меню-сообщение, если оно было
        data = await state.get_data()
        old_id = data.get(menu_flow.MENU_MESSAGE_KEY)
        if old_id:
            try:
                await message.bot.delete_message(message.chat.id, int(old_id))
            except Exception:
                pass
        sent = await message.answer(_start_text(), parse_mode="HTML", reply_markup=kb.main_menu())
        # это сообщение станет "актуальным меню": следующее нажатие кнопки его заменит
        await state.update_data(bot_menu_message_id=sent.message_id)

    @router.message(Command("watch"))
    async def on_watch(message: Message, state: FSMContext) -> None:
        if not is_admin(message.from_user.id if message.from_user else None, ctx):
            return
        url = _extract_url_arg(message)
        if not url:
            await state.set_state(AddStates.waiting_url)
            await render_menu(
                message,
                state,
                "Пришлите ссылку на раздел kufar.by с нужными фильтрами "
                "(или нажмите «◀️ Отмена»).",
                kb.wait_url_menu(),
            )
            return
        target = await watch_url(url, message, ctx)
        if target is not None:
            await reset_state_keep_menu(state)
            await render_menu(message, state, "👍 Главное меню:", kb.main_menu())

    @router.message(Command("list"))
    async def on_list(message: Message) -> None:
        if not is_admin(message.from_user.id if message.from_user else None, ctx):
            return
        targets = ctx.storage.load_targets()
        await message.answer(
            format_watch_list(list(targets.values())), parse_mode="HTML"
        )

    @router.message(Command("un"))
    async def on_un(message: Message) -> None:
        if not is_admin(message.from_user.id if message.from_user else None, ctx):
            return
        target_id = _parse_target_arg(message)
        targets = ctx.storage.load_targets()
        target = targets.pop(target_id, None)
        if target is None:
            await message.answer(format_error("Раздел с таким номером не найден."))
            return
        ctx.storage.save_targets(targets)
        await message.answer(f"🗑 Раздел #{target_id} «{target.label}» удалён.")

    @router.message(Command("pause"))
    async def on_pause(message: Message) -> None:
        if not is_admin(message.from_user.id if message.from_user else None, ctx):
            return
        target_id = _parse_target_arg(message)
        targets = ctx.storage.load_targets()
        target = targets.get(target_id)
        if target is None:
            await message.answer(format_error("Раздел с таким номером не найден."))
            return
        target.enabled = not target.enabled
        ctx.storage.save_targets(targets)
        state = "паузу" if not target.enabled else "работу"
        await message.answer(
            f"⏸ Раздел #{target_id} «{target.label}» переведён на {state}."
        )

    dp.include_router(router)
    # Кнопки подключаем после команд, чтобы команды имели приоритет.
    setup_button_handlers(dp, ctx)


def _start_text() -> str:
    return (
        "👋 <b>KufarBot</b>\n\n"
        "Пришлите мне ссылку на раздел kufar.by (или re.kufar.by) с нужными фильтрами:\n"
        "<code>/watch https://www.kufar.by/l/fotoapparaty/ft~fujifilm?sort=lst.d</code>\n\n"
        "Или используйте кнопки под строкой ввода:\n"
        f"• {kb.BTN_SECTIONS} — список разделов: выбрать → удалить/пауза\n"
        f"• {kb.BTN_ADD} — добавить раздел по ссылке\n\n"
        "Команды:\n"
        "/list — список разделов\n"
        "/pause &lt;номер&gt; — пауза / возобновить\n"
        "/un &lt;номер&gt; — удалить раздел"
    )


# ---------- helpers ----------


def _extract_url_arg(message: Message) -> str | None:
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    return parts[1].strip().strip("<>")


def _parse_target_arg(message: Message) -> int:
    text = (message.text or "").strip()
    parts = text.split()
    if len(parts) < 2:
        return -1
    try:
        return int(parts[1])
    except ValueError:
        return -1