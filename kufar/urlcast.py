"""Декодирование 'красивого' URL kufar.by в параметры внутреннего API.

Самый надёжный способ — не расшифровывать слаг категории и фильтры пути вручную
(они меняются), а взять готовые параметры из ``__NEXT_DATA__.props.initialState.
router.query`` — ровно те же параметры, которые сайт собирает и передаёт в API.
Такой декодинг всегда консистентен с тем, что видит пользователь на сайте.
"""
from __future__ import annotations

import json
import re
from typing import Tuple
from urllib.parse import urlsplit

import requests

KUFAR_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru,en;q=0.8",
}

ALLOWED_HOSTS = {"www.kufar.by", "kufar.by", "auto.kufar.by", "re.kufar.by"}


class KufarUrlDecodeError(Exception):
    """Ошибка при разборе ссылки kufar.by."""


def _extract_next_data(text: str) -> Optional[dict]:
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _validate_kufar_url(url: str) -> None:
    """Разрешаем только ссылки на kufar.by (защита от SSRF)."""
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError as exc:
        raise KufarUrlDecodeError("Некорректная ссылка.") from exc
    if host not in ALLOWED_HOSTS:
        raise KufarUrlDecodeError("Разрешены только ссылки на kufar.by.")


def decode_search_url(url: str, timeout: int = 20) -> Tuple[dict[str, str], int]:
    """Возвращает (query_params, status_code).

    ``query_params`` — словарь параметров для API поиска (cat, sort, query, prc, ...).
    Если страница не загрузилась — пробуем вытащить параметры из самого url,
    насколько это возможно.
    """
    _validate_kufar_url(url)

    try:
        resp = requests.get(url, headers=KUFAR_HEADERS, timeout=timeout)
    except requests.RequestException as exc:
        raise KufarUrlDecodeError(f"Не удалось открыть ссылку: {exc}") from exc

    if resp.status_code != 200:
        raise KufarUrlDecodeError(f"Не удалось открыть ссылку (HTTP {resp.status_code})")

    data = _extract_next_data(resp.text)
    params: dict[str, str] = {}

    if data is not None:
        try:
            query = data["props"]["initialState"]["router"]["query"]
            if isinstance(query, dict):
                # избавляемся от мусора; оставляем только строки / числа
                for key, value in query.items():
                    if value is None:
                        continue
                    if isinstance(value, bool):
                        params[key] = "1" if value else "0"
                    elif isinstance(value, (str, int, float)):
                        if isinstance(value, str) and not value.strip():
                            continue  # пустые значения ломают API (напр. rgn='')
                        params[key] = str(value)
        except (KeyError, TypeError):
            pass

    if not params:
        # У некоторых страниц нет __NEXT_DATA__ — берём хоть query-строку.
        from urllib.parse import parse_qs, urlsplit

        qs = parse_qs(urlsplit(url).query)
        for key, values in qs.items():
            if values:
                params[key] = values[0]

    # убираем пустые значения — они ломают API (напр. rgn='')
    params = {k: v for k, v in params.items() if v is not None and str(v).strip() != ""}

    params.setdefault("lang", "ru")
    params.setdefault("size", "30")
    if "sort" not in params:
        params["sort"] = "lst.d"

    return params, resp.status_code


def search_params_to_string(params: dict[str, str]) -> str:
    """Собираем содержательную строку описания поисковой ссылки для UI."""
    parts = []
    if params.get("typ") == "let":
        parts.append("аренда")
    if params.get("cat"):
        parts.append(f"кат. {params['cat']}")
    if params.get("query"):
        parts.append(f"запрос «{params['query']}»")
    if params.get("prc"):
        cur = {"USD": "$", "EUR": "€", "BYN": "р."}.get(params.get("cur", ""), "")
        suffix = f" {cur}" if cur else ""
        parts.append(f"цена {params['prc']}{suffix}")
    if params.get("rgn"):
        parts.append(f"регион {params['rgn']}")
    label = ", ".join(parts) if parts else "весь раздел"
    return label