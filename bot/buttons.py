"""Обработчики reply-клавиатуры (кнопки под строкой ввода).

Чтобы чат не засорялся: нажатия кнопок удаляются, а служебные сообщения бота
заменяют предыдущие (см. bot/menu_flow.py). Содержательные сообщения
(подтверждение добавления, уведомления о новых объявлениях) остаются в чате.
"""
from __future__ import annotations

import html as html_mod
import logging

from aiogram import Dispatcher, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot import keyboards as kb
from bot.context import BotContext
from bot.menu_flow import delete_press, render_menu, reset_state_keep_menu
from bot.notifier import format_error
from bot.watch_service import is_admin, watch_url
from kufar.urlcast import search_params_to_string

log = logging.getLogger(__name__)


class AddStates(StatesGroup):
    """FSM-состояния работы с кнопками."""

    waiting_url = State()


def _admin(message: Message, ctx: BotContext) -> bool:
    return is_admin(message.from_user.id if message.from_user else None, ctx)


def setup_button_handlers(dp: Dispatcher, ctx: BotContext) -> None:
    """Регистрирует обработчики кнопок. Включать ПОСЛЕ командного роутера."""
    router = Router()

    @router.message(F.text == kb.BTN_SECTIONS)
    async def on_sections(message: Message, state: FSMContext) -> None:
        if not _admin(message, ctx):
            return
        await delete_press(message)
        await reset_state_keep_menu(state)
        targets = list(ctx.storage.load_targets().values())
        if targets:
            await render_menu(
                message, state, "📋 Ваши разделы — выберите один:", kb.targets_menu(targets)
            )
        else:
            await render_menu(
                message,
                state,
                "📭 Отслеживаемых разделов пока нет.\n"
                "Нажмите «➕ Добавить раздел» и пришлите ссылку на kufar.by.",
                kb.main_menu(),
            )

    @router.message(F.text == kb.BTN_ADD)
    async def on_add(message: Message, state: FSMContext) -> None:
        if not _admin(message, ctx):
            return
        await delete_press(message)
        await state.set_state(AddStates.waiting_url)
        await render_menu(
            message,
            state,
            "➕ Пришлите ссылку на раздел kufar.by с нужными фильтрами, например:\n"
            "<code>https://www.kufar.by/l/fotoapparaty/ft~fujifilm?sort=lst.d</code>\n\n"
            "Или нажмите «◀️ Отмена».",
            kb.wait_url_menu(),
            parse_mode="HTML",
        )

    @router.message(F.text == kb.BTN_HELP)
    async def on_help(message: Message, state: FSMContext) -> None:
        if not _admin(message, ctx):
            return
        await delete_press(message)
        await reset_state_keep_menu(state)
        await render_menu(message, state, _help_text(), kb.main_menu(), parse_mode="HTML")

    @router.message(F.text == kb.BTN_CANCEL)
    async def on_cancel(message: Message, state: FSMContext) -> None:
        if not _admin(message, ctx):
            return
        await delete_press(message)
        await reset_state_keep_menu(state)
        await render_menu(message, state, "👌 Главное меню:", kb.main_menu())

    # ---------- выбор раздела и действия ----------

    @router.message(F.text.startswith("#"))
    async def on_select_target(message: Message, state: FSMContext) -> None:
        if not _admin(message, ctx):
            return
        await delete_press(message)
        target_id = kb.parse_target_from_button(message.text or "")
        target = ctx.storage.load_targets().get(target_id or -1)
        if target is None:
            await reset_state_keep_menu(state)
            await render_menu(
                message,
                state,
                format_error("Раздел не найден (возможно, уже удалён)."),
                kb.main_menu(),
                parse_mode="HTML",
            )
            return
        data = await state.get_data()
        await state.set_data({**data, "selected_id": target.target_id})
        status = "⏸ на паузе" if not target.enabled else "🟢 активен"
        desc = search_params_to_string(target.params)
        await render_menu(
            message,
            state,
            f"#{target.target_id} <b>{html_mod.escape(target.label)}</b>\n"
            f"Статус: {status}\n"
            f"Фильтры: {html_mod.escape(desc)}\n"
            f"<i>{html_mod.escape(target.url)}</i>\n\n"
            f"Выберите действие:",
            kb.target_actions_menu(target),
            parse_mode="HTML",
        )

    @router.message(F.text.startswith(kb.BTN_DELETE_PREFIX))
    async def on_delete(message: Message, state: FSMContext) -> None:
        if not _admin(message, ctx):
            return
        await delete_press(message)
        target_id = kb.parse_target_from_button(message.text or "")
        targets = ctx.storage.load_targets()
        target = targets.pop(target_id or -1, None)
        if target is None:
            note = format_error("Раздел не найден.")
        else:
            ctx.storage.save_targets(targets)
            note = f"🗑 Раздел #{target_id} «{target.label}» удалён."
        await _back_to_sections(message, state, ctx, note)

    @router.message(F.text.startswith(kb.BTN_PAUSE_PREFIX))
    @router.message(F.text.startswith(kb.BTN_RESUME_PREFIX))
    async def on_toggle_pause(message: Message, state: FSMContext) -> None:
        if not _admin(message, ctx):
            return
        await delete_press(message)
        target_id = kb.parse_target_from_button(message.text or "")
        targets = ctx.storage.load_targets()
        target = targets.get(target_id or -1)
        if target is None:
            await _back_to_sections(message, state, ctx, format_error("Раздел не найден."))
            return
        target.enabled = not target.enabled
        ctx.storage.save_targets(targets)
        action = "⏸ Поставлен на паузу" if not target.enabled else "▶️ Возобновлён"
        await render_menu(
            message,
            state,
            f"{action} раздел #{target_id} «{html_mod.escape(target.label)}».\n\nВыберите действие:",
            kb.target_actions_menu(target),
            parse_mode="HTML",
        )

    async def _back_to_sections(
        message: Message, state: FSMContext, ctx: BotContext, note: str
    ) -> None:
        await reset_state_keep_menu(state)
        targets = list(ctx.storage.load_targets().values())
        if targets:
            await render_menu(
                message,
                state,
                f"{note}\n\n📋 Ваши разделы:",
                kb.targets_menu(targets),
            )
        else:
            await render_menu(
                message,
                state,
                f"{note}\n\n📭 Отслеживаемых разделов больше нет.",
                kb.main_menu(),
            )

    # ---------- фолбэк: ссылки и прочий текст ----------

    @router.message(F.text)
    async def on_fallback_text(message: Message, state: FSMContext) -> None:
        if not _admin(message, ctx):
            return
        text = (message.text or "").strip()

        if text.startswith("/"):
            await reset_state_keep_menu(state)
            await render_menu(
                message,
                state,
                "Неизвестная команда. Посмотрите /start или используйте кнопки 👇",
                kb.main_menu(),
            )
            return

        looks_like_url = text.lower().startswith("http")
        current_state = await state.get_state()

        if looks_like_url:
            target = await watch_url(text, message, ctx)
            if target is not None:
                await reset_state_keep_menu(state)
                await render_menu(message, state, "👍 Главное меню:", kb.main_menu())
            # при ошибке watch_url сам сообщил подробности; остаёмся в текущем состоянии
            return

        if current_state == AddStates.waiting_url.state:
            await render_menu(
                message,
                state,
                "Это не похоже на ссылку. Пришлите ссылку вида "
                "<code>https://www.kufar.by/l/...</code> или нажмите «◀️ Отмена».",
                kb.wait_url_menu(),
                parse_mode="HTML",
            )
            return

        await render_menu(message, state, "Выберите действие на клавиатуре 👇", kb.main_menu())

    dp.include_router(router)


def _help_text() -> str:
    return (
        "👋 <b>KufarBot</b>\n\n"
        "Пришлите мне ссылку на раздел kufar.by (или re.kufar.by) с нужными фильтрами:\n"
        "<code>/watch https://www.kufar.by/l/fotoapparaty/ft~fujifilm?sort=lst.d</code>\n\n"
        "Или используйте кнопки:\n"
        f"• {kb.BTN_SECTIONS} — список разделов: выбрать → удалить/пауза\n"
        f"• {kb.BTN_ADD} — добавить раздел по ссылке\n\n"
        "Команды:\n"
        "/list — список разделов\n"
        "/pause &lt;номер&gt; — пауза / возобновить\n"
        "/un &lt;номер&gt; — удалить раздел"
    )