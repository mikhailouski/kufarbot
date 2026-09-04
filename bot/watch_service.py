"""Служебные операции с разделами (общие для команд и кнопок)."""
from __future__ import annotations

import asyncio
import logging
from functools import partial
from urllib.parse import urlsplit

from aiogram.types import Message

from bot.context import BotContext
from bot.notifier import format_error, format_watch_added
from kufar.client import KufarClient
from kufar.urlcast import KufarUrlDecodeError, decode_search_url
from storage import WatchTarget

log = logging.getLogger(__name__)


def is_admin(user_id: int | None, ctx: BotContext) -> bool:
    if user_id == ctx.admin_id:
        return True
    log.warning("Отказ в доступе пользователю id=%s", user_id)
    return False


def label_from_url(url: str, params: dict[str, str]) -> str:
    path = urlsplit(url).path.rstrip("/")
    last_segment = path.split("/")[-1] if path else ""
    if last_segment and "~" not in last_segment:
        return last_segment
    return params.get("cat") or last_segment or url


async def watch_url(url: str, message: Message, ctx: BotContext) -> WatchTarget | None:
    """Декодирует ссылку и добавляет раздел. Отвечает пользователю.

    Возвращает созданный WatchTarget или None, если добавить не удалось.
    """
    try:
        params, _ = await _decode_in_thread(url)
    except KufarUrlDecodeError as exc:
        await message.answer(format_error(str(exc)))
        return None
    except Exception as exc:
        log.exception("Ошибка декодирования ссылки")
        await message.answer(format_error(f"Не удалось получить данные по ссылке: {exc}"))
        return None

    targets = ctx.storage.load_targets()
    for target in targets.values():
        if target.url.strip().lower() == url.strip().lower():
            await message.answer(
                format_error(f"Этот раздел уже отслеживается (номер #{target.target_id}).")
            )
            return None

    target = WatchTarget(
        target_id=ctx.storage.next_target_id(targets),
        url=url,
        label=label_from_url(url, params),
        params=params,
        enabled=True,
        baseline_established=False,
    )
    targets[target.target_id] = target
    ctx.storage.save_targets(targets)
    await message.answer(format_watch_added(target), parse_mode="HTML")
    return target


async def _decode_in_thread(url: str) -> tuple[dict[str, str], int]:
    """Выполняем сетевой sync-декодер в потоке, чтобы не блокировать event loop."""
    fn = partial(decode_search_url, url)
    return await asyncio.to_thread(fn)