"""Клиент внутреннего API поиска объявлений kufar.by."""
from __future__ import annotations

from typing import Optional

import requests

from kufar.models import AdListing, ad_from_json

SEARCH_URL = "https://cre-api.kufar.by/ads-search/v1/engine/v1/search/rendered-paginated"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "ru,en;q=0.8",
}


class KufarClient:
    """Тонкий клиент к поисковому API kufar.by."""

    def __init__(self, headers: Optional[dict] = None, timeout: int = 20, retries: int = 3):
        self.headers = {**DEFAULT_HEADERS, **(headers or {})}
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def fetch_ads(
        self,
        params: dict[str, str],
        size: int = 30,
        cursor: str = "",
    ) -> list[AdListing]:
        # ВАЖНО: параметр size должен перебивать дефолт, но не трогаем остальные фильтры.
        query_params = {**params}
        query_params["size"] = str(size)
        if cursor:
            query_params["cursor"] = cursor
        query_params.setdefault("lang", "ru")
        query_params.setdefault("sort", "lst.d")

        # пустые значения ломают API
        query_params = {k: v for k, v in query_params.items() if v is not None and str(v).strip() != ""}

        last_response = None
        for attempt in range(self.retries):
            try:
                resp = self.session.get(SEARCH_URL, params=query_params, timeout=self.timeout)
                last_response = resp
                if resp.status_code == 200:
                    payload = resp.json()
                    ads = payload.get("ads") or []
                    return [ad_from_json(a) for a in ads]
            except (requests.RequestException, ValueError):
                pass
        raise RuntimeError(
            f"API поиска не ответил (HTTP {getattr(last_response, 'status_code', '?')})"
        )

    def fetch_ads_raw(self, params: dict[str, str], size: int = 30) -> list[dict]:
        """Сырые dict-объявления (для debug)."""
        query_params = {**params, "size": str(size)}
        resp = self.session.get(SEARCH_URL, params=query_params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get("ads", [])

    def close(self):
        self.session.close()


__all__ = ["KufarClient", "SEARCH_URL", "AdListing", "ad_from_json"]