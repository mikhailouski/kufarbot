"""Обработчики команд Telegram-бота."""
from __future__ import annotations

import logging

from aiogram import Dispatcher, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.notifier import format_error, format_watch_added, format_watch_list
from kufar.client import KufarClient
from kufar.urlcast import KufarUrlDecodeError, decode_search_url
from storage import Storage, WatchTarget

log = logging.getLogger(__name__)


class BotContext:
    """Держим зависимости, доступные обработчикам."""

    def __init__(
        self,
        admin_id: int,
        storage: Storage,
        client: KufarClient,
    ):
        self.admin_id = admin_id
        self.storage = storage
        self.client = client


def setup_handlers(dp: Dispatcher, ctx: "BotContext") -> None:
    """Регистрирует все команды бота."""
    router = Router()

    @router.message(CommandStart())
    async def on_start(message: Message) -> None:
        if not _is_admin(message, ctx):
            await message.answer("⛔ У вас нет доступа к этому боту.")
            return
        await message.answer(
            "👋 <b>KufarBot</b>\n\n"
            "Пришлите мне ссылку на раздел kufar.by с нужными фильтрами:\n"
            "<code>/watch https://www.kufar.by/l/fotoapparaty/ft~fujifilm?sort=lst.d</code>\n\n"
            "Другие команды:\n"
            "/list — показать отслеживаемые разделы\n"
            "/pause &lt;номер&gt; — поставить на паузу / возобновить\n"
            "/un &lt;номер&gt; — удалить раздел",
            parse_mode="HTML",
        )

    @router.message(Command("watch"))
    async def on_watch(message: Message) -> None:
        if not _is_admin(message, ctx):
            return
        url = _extract_url_arg(message)
        if not url:
            await message.answer(
                "Укажите ссылку на раздел kufar, например:\n"
                "<code>/watch https://www.kufar.by/l/fotoapparaty?sort=lst.d</code>",
                parse_mode="HTML",
            )
            return
        await _watch_url(url, message, ctx)

    @router.message(Command("list"))
    async def on_list(message: Message) -> None:
        if not _is_admin(message, ctx):
            return
        targets = ctx.storage.load_targets()
        await message.answer(
            format_watch_list(list(targets.values())), parse_mode="HTML"
        )

    @router.message(Command("un"))
    async def on_un(message: Message) -> None:
        if not _is_admin(message, ctx):
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
        if not _is_admin(message, ctx):
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


# ---------- helpers ----------


def _is_admin(message: Message, ctx: "BotContext") -> bool:
    if message.from_user and message.from_user.id == ctx.admin_id:
        return True
    log.warning("Отказ в доступе пользователю id=%s", getattr(message.from_user, "id", None))
    return False


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


def _label_from_url(url: str, params: dict[str, str]) -> str:
    from urllib.parse import urlsplit

    path = urlsplit(url).path.rstrip("/")
    last_segment = path.split("/")[-1] if path else ""
    if last_segment and "~" not in last_segment:
        return last_segment
    return params.get("cat") or last_segment or url


async def _watch_url(url: str, message: Message, ctx: "BotContext") -> None:
    try:
        params, _ = await _decode_in_thread(url)
    except KufarUrlDecodeError as exc:
        await message.answer(format_error(str(exc)))
        return
    except Exception as exc:
        log.exception("Ошибка декодирования ссылки")
        await message.answer(format_error(f"Не удалось получить данные по ссылке: {exc}"))
        return

    targets = ctx.storage.load_targets()
    for target in targets.values():
        if target.url.strip().lower() == url.strip().lower():
            await message.answer(
                format_error(f"Этот раздел уже отслеживается (номер #{target.target_id}).")
            )
            return

    target = WatchTarget(
        target_id=ctx.storage.next_target_id(targets),
        url=url,
        label=_label_from_url(url, params),
        params=params,
        enabled=True,
        baseline_established=False,
    )
    targets[target.target_id] = target
    ctx.storage.save_targets(targets)
    await message.answer(format_watch_added(target), parse_mode="HTML")


async def _decode_in_thread(url: str) -> tuple[dict[str, str], int]:
    """Выполняем сетевой sync-декодер в потоке, чтобы не блокировать event loop."""
    import asyncio
    from functools import partial

    fn = partial(decode_search_url, url)
    return await asyncio.to_thread(fn)