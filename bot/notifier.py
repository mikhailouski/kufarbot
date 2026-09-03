"""Формирование и отправка уведомлений о новых объявлениях."""
from __future__ import annotations

import html as html_mod

from aiogram import Bot

from kufar.models import AdListing
from kufar.urlcast import search_params_to_string
from storage import WatchTarget


def format_ad_text(ad: AdListing) -> str:
    """Краткое описание объявления для сообщения в Telegram."""
    lines = [f"📷 <b>{html_mod.escape(ad.subject)}</b>"]

    if ad.price_byn is not None:
        price = f"{ad.price_byn:,.0f}".replace(",", " ") + " р."
        if ad.price_usd and ad.price_usd > 0:
            price += f"  (≈{ad.price_usd:,.0f} USD)".replace(",", " ")
        lines.append(f"💰 {price}")
    else:
        lines.append("💰 Договорная")

    location = ad.location
    if location:
        lines.append(f"📍 {html_mod.escape(location)}")

    lines.append(
        f"🔗 <a href=\"{html_mod.escape(ad.link, quote=False)}\">Открыть объявление</a>"
    )
    return "\n".join(lines)


def format_error(text: str) -> str:
    return f"⚠️ {text}"


def format_watch_added(target: WatchTarget) -> str:
    desc = search_params_to_string(target.params)
    return (
        f"✅ Раздел добавлен!\n\n"
        f"#{target.target_id} — <b>{html_mod.escape(target.label)}</b>\n"
        f"Фильтры: {html_mod.escape(desc)}\n\n"
        f"Начну присылать объявления, которые <b>появятся после</b> подключения. "
        f"Существующие не буду рассылать."
    )


def format_watch_list(targets: list[WatchTarget]) -> str:
    if not targets:
        return "📭 Отслеживаемых разделов пока нет.\nДобавьте командой:\n/watch &lt;ссылка_на_раздел_kufar&gt;"
    lines = ["📋 <b>Отслеживаемые разделы:</b>\n"]
    for target in targets:
        lines.append(target.short_label)
        lines.append(f"   <i>{html_mod.escape(target.url)}</i>")
    lines.append("\nПауза: /pause х     Удалить: /un х")
    return "\n".join(lines)


async def send_ad(ad: AdListing, bot: Bot, chat_id: int) -> None:
    """Отправляет одно объявление (с фото при наличии)."""
    text = format_ad_text(ad)
    if ad.image:
        try:
            await bot.send_photo(
                chat_id=chat_id,
                photo=ad.image,
                caption=text,
                parse_mode="HTML",
            )
            return
        except Exception:
            pass  # фото не загрузилось — отправим текстом
    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")