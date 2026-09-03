"""Модели данных объявлений kufar.by."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class AdListing:
    """Представление одного объявления из ответа API поиска kufar.by."""

    list_id: int
    subject: str
    link: str
    price_byn: Optional[float] = None
    price_usd: Optional[float] = None
    currency: str = "BYR"
    image: Optional[str] = None
    region: str = ""
    area: str = ""
    city: str = ""
    list_time: Optional[datetime] = None
    ad_params: list[dict] = field(default_factory=list)
    category: str = ""
    type: str = "sell"

    @property
    def location(self) -> str:
        """Локация как строка. Пример: 'Минск, Советский'."""
        return ", ".join(
            [part for part in (self.city or self.region, self.area) if part]
        ) or self.region or "Беларусь"


def _to_float(value) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value) / 100.0
    except (TypeError, ValueError):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


def _find_param(ad_params: list[dict], key: str) -> Optional[str]:
    """Ищем строкового значения параметра объявления по коду 'pu' или 'p'."""
    for param in ad_params:
        if not isinstance(param, dict):
            continue
        if param.get("pu") == key or param.get("p") == key:
            value = param.get("vl")
            if value:
                return str(value)
    return None


def _parse_list_time(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _extract_image(raw: dict) -> Optional[str]:
    """Преобразуем images → большой URL картинки."""
    images = raw.get("images")
    if not images:
        return None
    first = images[0]
    if not isinstance(first, dict):
        return None
    storage = first.get("media_storage", "rms")
    path = first.get("path")
    if not path:
        return None
    if storage == "rms":
        return f"https://rms.kufar.by/v1/gallery/{path}"
    if storage == "yams":
        image_id = first.get("id") or first.get("image_id")
        if image_id:
            return f"https://yams.kufar.by/api/v1/kufar-ads/images/{str(image_id)[:2]}/{image_id}.jpg?rule=gallery"
    # универсальный фолбэк
    return f"https://rms.kufar.by/v1/gallery/{path}"


def ad_from_json(raw: dict) -> AdListing:
    """Собираем AdListing из JSON-объекта объявления (API или __NEXT_DATA__)."""
    ad_params = [
        p for p in (raw.get("ad_parameters") or raw.get("adParams") or []) if isinstance(p, dict)
    ]
    price_byn = _to_float(raw.get("price_byn") or raw.get("price"))
    price_usd = _to_float(raw.get("price_usd") or raw.get("priceUsd"))

    region = _find_param(ad_params, "rgn") or _find_param(ad_params, "region") or ""
    area = _find_param(ad_params, "ar") or _find_param(ad_params, "area") or ""

    return AdListing(
        list_id=int(raw.get("list_id") or raw.get("ad_id") or 0),
        subject=raw.get("subject") or raw.get("title") or "Без названия",
        link=raw.get("ad_link") or f"https://www.kufar.by/item/{raw.get('ad_id') or ''}",
        price_byn=price_byn,
        price_usd=price_usd,
        currency=raw.get("currency") or "BYN",
        image=_extract_image(raw),
        region=region,
        area=area,
        list_time=_parse_list_time(raw.get("list_time")),
        ad_params=ad_params,
        category=str(raw.get("category") or _find_param(ad_params, "cat") or ""),
        type=raw.get("type") or "sell",
    )