"""Хранилище состояния бота (JSON): отслеживаемые разделы + отправленные list_id."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class WatchTarget:
    target_id: int
    url: str
    label: str
    params: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    baseline_established: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.target_id,
            "url": self.url,
            "label": self.label,
            "params": self.params,
            "enabled": self.enabled,
            "baseline_established": self.baseline_established,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WatchTarget":
        return cls(
            target_id=int(data.get("id", 0)),
            url=data.get("url", ""),
            label=data.get("label", ""),
            params=data.get("params") or {},
            enabled=bool(data.get("enabled", True)),
            baseline_established=bool(data.get("baseline_established", False)),
        )

    @property
    def short_label(self) -> str:
        status = "🟢" if self.enabled else "⏸"
        return f"{status} #{self.target_id} {self.label}"


class Storage:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Не удалось прочитать %s: %s", self.path, exc)
            return {}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ---------- targets ----------
    def load_targets(self) -> dict[int, WatchTarget]:
        raw = self._read().get("targets", [])
        targets: dict[int, WatchTarget] = {}
        for item in raw:
            try:
                target = WatchTarget.from_dict(item)
                targets[target.target_id] = target
            except (TypeError, ValueError) as exc:
                log.warning("Битая запись target: %s", exc)
        return targets

    def save_targets(self, targets: dict[int, WatchTarget]) -> None:
        data = self._read()
        data["targets"] = [t.to_dict() for t in targets.values()]
        self._write(data)

    # ---------- seen ids ----------
    def load_seen(self) -> set[int]:
        return set(self._read().get("seen_ids", []))

    def save_seen(self, seen: set[int]) -> None:
        data = self._read()
        data["seen_ids"] = sorted(seen)
        self._write(data)

    def next_target_id(self, targets: dict[int, WatchTarget]) -> int:
        if not targets:
            return 1
        return max(targets.keys()) + 1

    # ---------- базовая отладка ----------
    def touch(self) -> None:
        self._write(self._read())


__all__ = ["Storage", "WatchTarget"]