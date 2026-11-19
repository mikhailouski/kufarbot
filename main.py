"""Точка входа KufarBot.

Запускает Telegram-бота (aiogram) и фоновый цикл мониторинга:
каждые CHECK_INTERVAL секунд опрашивает API Kufar по отслеживаемым разделам
и присылает администратору новые объявления.

HTTP health endpoints:
  GET /health/live  — процесс и фоновая задача мониторинга работают.
  GET /health/ready — Telegram polling запущен, задача мониторинга активна.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher

from bot.context import BotContext
from bot.handlers import setup_handlers
from bot.notifier import send_ad
from config import DATA_DIR, load_config
from kufar.client import KufarClient
from storage import Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("kufarbot")


HEALTH_HOST = "0.0.0.0"
HEALTH_PORT = 8080


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
                log.info(
                    "Достигнут лимит отправок за цикл (%d)",
                    cfg.max_send_per_check,
                )
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
            # Полное ожидание, чтобы останов был чистым.
            await asyncio.sleep(cfg.check_interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # Не даём фоновой задаче завершиться из-за ошибки.
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

    # Состояние используется HTTP-обработчиком health checks.
    polling_started = False
    monitor_task: asyncio.Task | None = None

    async def health_handler(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Минимальный HTTP-обработчик для Kubernetes probes."""
        status = 404
        body = b"not found\n"

        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=2)
            parts = request_line.decode("ascii", errors="replace").split()

            # Читаем заголовки до пустой строки.
            while True:
                header = await asyncio.wait_for(reader.readline(), timeout=2)
                if header in (b"\r\n", b"\n", b""):
                    break

            if len(parts) >= 2:
                path = parts[1].split("?", 1)[0]

                monitor_active = (
                    monitor_task is not None and not monitor_task.done()
                )

                if path == "/health/live":
                    # Если фоновая задача неожиданно завершилась, Pod нужно
                    # перезапустить. Зависимость от Telegram/Kufar здесь
                    # намеренно не проверяется.
                    status = 200 if monitor_active else 503
                    body = b"ok\n" if status == 200 else b"monitor task stopped\n"

                elif path == "/health/ready":
                    # Готовность означает, что aiogram запустил polling,
                    # а фоновая задача мониторинга всё ещё активна.
                    ready = polling_started and monitor_active
                    status = 200 if ready else 503
                    body = b"ready\n" if ready else b"not ready\n"

            reason = {
                200: "OK",
                404: "Not Found",
                503: "Service Unavailable",
            }[status]

            response = (
                f"HTTP/1.1 {status} {reason}\r\n"
                "Content-Type: text/plain; charset=utf-8\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode("ascii") + body

            writer.write(response)
            await writer.drain()

        except (asyncio.TimeoutError, ConnectionError, BrokenPipeError):
            # Клиент проверки мог закрыть соединение или не прислать запрос.
            pass
        finally:
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()

    async def on_startup(bot: Bot) -> None:
        nonlocal polling_started
        polling_started = True
        log.info("Health check: Telegram polling запущен.")

    # Событие вызывается aiogram при запуске polling.
    dp.startup.register(on_startup)

    # HTTP-пробы Kubernetes обращаются к Pod IP, поэтому слушаем все
    # интерфейсы контейнера. Service/Ingress для этого порта не создаём.
    health_server = await asyncio.start_server(
        health_handler,
        host=HEALTH_HOST,
        port=HEALTH_PORT,
    )
    log.info(
        "Health check HTTP server слушает %s:%d",
        HEALTH_HOST,
        HEALTH_PORT,
    )

    # Запускаем мониторинг до обращения к Telegram: liveness не должен
    # зависеть от доступности внешнего API.
    monitor_task = asyncio.create_task(monitor_loop(bot, ctx, cfg))

    # Если у бота активен webhook, polling не сможет получать обновления
    # (TelegramConflictError). Сбрасываем webhook перед стартом polling.
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        log.info("Webhook удалён (поллинг активен).")
    except Exception as exc:
        log.warning("Не удалось удалить webhook: %s", exc)

    log.info(
        "Запускаю поллинг бота (admin=%s, interval=%ss)...",
        cfg.admin_user_id,
        cfg.check_interval,
    )

    try:
        await dp.start_polling(bot)
    finally:
        polling_started = False

        health_server.close()
        await health_server.wait_closed()

        monitor_task.cancel()
        with suppress(asyncio.CancelledError):
            await monitor_task

        client.close()  # Синхронный метод requests.Session.
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Остановлено пользователем.")
