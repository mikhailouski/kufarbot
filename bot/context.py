"""Общий контекст бота (зависимости, доступные обработчикам)."""
from __future__ import annotations

from kufar.client import KufarClient
from storage import Storage


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