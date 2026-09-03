"""Точка входа KufarBot.

Запускает Telegram-бота (aiogram) и фоновый цикл мониторинга:
каждые CHECK_INTERVAL секунд опрашивает API kufar по отслеживаемым разделам
и присылает администратору новые объявления.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher

from bot.handlers import BotContext, setup_handlers
from bot.notifier import send_ad
from config import DATA_DIR, load_config
from kufar.client import KufarClient
from storage import Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("kufarbot")


async def poll_once(bot, ctx: BotContext, cfg) -> None:
    """Один проход мониторинга всех отслеживаемых разделов."""
    storage = ctx.storage
    client = ctx.client

    targets = storage.load_targets()
    enabled = [t for t in targets.values() if t.enabled]
    if not enabled:
        return

    log.info("Проверяю %d разделов...", len(enabled))
    sent_total = 0
    for target in enabled:
        try:
            ads = await asyncio.to_thread(
                client.fetch_ads, target.params, cfg.check_size
            )
        except Exception as exc:
            log.warning("Раздел #%d: ошибка запроса: %s", target.target_id, exc)
            continue

        if not target.baseline_established:
            # Первый замер — просто фиксируем текущую выборку как базовую.
            seen = storage.load_seen()
            for ad in ads:
                seen.add(ad.list_id)
            storage.save_seen(seen)
            target.baseline_established = True
            storage.save_targets(targets)
            log.info(
                "Раздел #%d «%s»: baseline зафиксирован (%d объявл.)",
                target.target_id, target.label, len(ads),
            )
            continue

        seen = storage.load_seen()
        new_ads = [ad for ad in ads if ad.list_id not in seen]
        new_ads.sort(key=lambda ad: ad.list_time or _epoch(), reverse=True)

        for ad in new_ads:
            if sent_total >= cfg.max_send_per_check:
                log.info("Достигнут лимит отправок за цикл (%d)", cfg.max_send_per_check)
                break
            seen.add(ad.list_id)
            await send_ad(ad, bot, cfg.admin_user_id)
            sent_total += 1

        storage.save_seen(seen)


async def monitor_loop(bot: Bot, ctx: BotContext, cfg) -> None:
    """Бесконечный цикл проверки новых объявлений."""
    while True:
        try:
            await poll_once(bot, ctx, cfg)
            # полное ожидание, чтобы останов был чистым
            await asyncio.sleep(cfg.check_interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # никогда не даём упасть фоновому циклу
            log.exception("Ошибка в цикле мониторинга: %s", exc)
            await asyncio.sleep(cfg.check_interval)


def _epoch() -> datetime:
    return datetime.fromtimestamp(0, tz=timezone.utc)


async def main() -> None:
    cfg = load_config()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    bot = Bot(token=cfg.bot_token)
    dp = Dispatcher()

    storage = Storage(DATA_DIR / "bot_state.json")
    client = KufarClient()
    ctx = BotContext(admin_id=cfg.admin_user_id, storage=storage, client=client)

    setup_handlers(dp, ctx)

    # Если у бота активен webhook, поллинг не сможет получать обновления
    # (TelegramConflictError). Сбрасываем webhook перед стартом, чтобы
    # бот всегда работал через long-polling.
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        log.info("Webhook удалён (поллинг активен).")
    except Exception as exc:
        log.warning("Не удалось удалить webhook: %s", exc)

    bg_task = asyncio.create_task(monitor_loop(bot, ctx, cfg))

    log.info("Запускаю поллинг бота (admin=%s, interval=%ss)...", cfg.admin_user_id, cfg.check_interval)
    try:
        await dp.start_polling(bot)
    finally:
        bg_task.cancel()
        with suppress(asyncio.CancelledError):
            await bg_task
        client.close()  # синхронный метод requests.Session
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Остановлено пользователем.")