"""Лёгкие юнит-тесты без внешних сетевых зависимостей.

Можно гонять: py -m unittest tests.test_core
"""
from __future__ import annotations

import json
import logging
import tempfile
import unittest
from pathlib import Path

# Модуль main логирует в stderr (logging), из-за чего PowerShell показывает
# ложный exit code 1 при прогоне тестов. Подавляем логи категории бота.
logging.getLogger("kufarbot").setLevel(logging.CRITICAL)
logging.getLogger("kufar").setLevel(logging.CRITICAL)
from unittest import mock

from kufar import client as client_mod
from kufar import models
from kufar import urlcast
from storage import Storage, WatchTarget

SAMPLE_AD = {
    "list_id": 1082357726,
    "subject": "Фотоаппарат Fujifilm x-t50",
    "ad_link": "https://www.kufar.by/item/1082357726",
    "price_byn": "350000",
    "price_usd": "117623",
    "currency": "BYR",
    "list_time": "2026-08-24T12:49:54Z",
    "category": "5070",
    "images": [
        {
            "media_storage": "rms",
            "path": "adim1/b18dd3ba-28d4-465e-8ce0-131dc7ef5cd4.jpg",
        }
    ],
    "ad_parameters": [
        {"pl": "Регион", "vl": "Минск", "p": "region", "v": 7, "pu": "rgn"},
        {"pl": "Город / Район", "vl": "Центральный", "p": "area", "v": "2", "pu": "ar"},
    ],
}


class ModelsTest(unittest.TestCase):
    def test_ad_from_json(self):
        ad = models.ad_from_json(SAMPLE_AD)
        self.assertEqual(ad.list_id, 1082357726)
        self.assertEqual(ad.subject, "Фотоаппарат Fujifilm x-t50")
        self.assertAlmostEqual(ad.price_byn or 0, 3500.0)
        self.assertAlmostEqual(ad.price_usd or 0, 1176.23)
        self.assertEqual(ad.location, "Минск, Центральный")
        self.assertEqual(ad.link, "https://www.kufar.by/item/1082357726")
        self.assertIn("rms.kufar.by/v1/gallery", ad.image or "")


class StorageTest(unittest.TestCase):
    def test_target_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "bot_state.json")
            targets = {
                1: WatchTarget(
                    target_id=1,
                    url="https://www.kufar.by/l/x",
                    label="x",
                    params={"cat": "5", "sort": "lst.d"},
                    enabled=True,
                    baseline_established=False,
                )
            }
            storage.save_targets(targets)
            seen = {1, 2, 3}
            seen.add(1082357726)
            storage.save_seen(seen)

            reloaded = storage.load_targets()
            self.assertEqual(reloaded[1].url, "https://www.kufar.by/l/x")
            self.assertEqual(reloaded[1].params["cat"], "5")
            self.assertFalse(reloaded[1].baseline_established)
            self.assertEqual(storage.load_seen(), {1, 2, 3, 1082357726})

    def test_next_id(self):
        storage = Storage(Path("nonexistent.json"))
        targets = {1: WatchTarget(1, "u", "l"), 5: WatchTarget(5, "u", "l")}
        self.assertEqual(storage.next_target_id(targets), 6)


class UrlcastTest(unittest.TestCase):
    def test_extract_next_data(self):
        html = '<html><script id="__NEXT_DATA__">{"props":{}}</script></html>'
        self.assertIsNotNone(urlcast._extract_next_data(html))

    def test_decode_prunes_empty(self):
        data = {
            "props": {
                "initialState": {
                    "router": {
                        "query": {
                            "cat": "5070",
                            "sort": "lst.d",
                            "prc": "r:100000,100000000000",
                            "rgn": "",
                            "flag": None,
                            "bool_f": True,
                        }
                    }
                }
            }
        }
        fake_resp = mock.Mock()
        fake_resp.status_code = 200
        fake_resp.text = (
            '<script id="__NEXT_DATA__">' + json.dumps(data).replace("</", "<\\/") + "</script>"
        )
        with mock.patch("requests.get", return_value=fake_resp):
            params, status = urlcast.decode_search_url("https://www.kufar.by/l/x")
        self.assertEqual(status, 200)
        self.assertEqual(params["cat"], "5070")
        self.assertIn("prc", params)
        self.assertNotIn("rgn", params)  # пустые выкинули
        self.assertEqual(params.get("bool_f"), "1")  # bool -> "1"
        self.assertIn("lang", params)

    def test_rejects_non_kufar_host(self):
        with self.assertRaises(urlcast.KufarUrlDecodeError):
            urlcast.decode_search_url("https://evil.example.com/l/x")

        fake_resp = mock.Mock()
        fake_resp.status_code = 200
        fake_resp.text = "<html></html>"
        with mock.patch("requests.get", return_value=fake_resp):
            _, status = urlcast.decode_search_url("https://www.kufar.by/l/x")
        self.assertEqual(status, 200)


class ClientTest(unittest.TestCase):
    def test_fetch_ads_empties_query_and_parses(self):
        payload = {"ads": [SAMPLE_AD], "total": 1, "pagination": None}
        fake = mock.Mock()
        fake.status_code = 200
        fake.json.return_value = payload
        captured = {}

        def fake_get(*args, **kwargs):
            captured["params"] = kwargs.get("params") or (args[1] if len(args) > 1 else None)
            return fake

        with mock.patch.object(client_mod.requests.Session, "get", fake_get):
            ads = client_mod.KufarClient().fetch_ads({"cat": "5070"}, size=10)
        self.assertEqual(len(ads), 1)
        self.assertEqual(captured["params"]["size"], "10")
        self.assertEqual(ads[0].subject, "Фотоаппарат Fujifilm x-t50")


class FakeClient:
    """Заглушка API: возвращает заранее заданный набор объявлений."""

    def __init__(self, ads):
        self.ads = ads

    def fetch_ads(self, params, size=30, cursor=""):
        return list(self.ads)


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_photo(self, chat_id, photo, caption, parse_mode=None):
        self.sent.append(("photo", photo, caption))

    async def send_message(self, chat_id, text, parse_mode=None):
        self.sent.append(("text", None, text))


class MonitorTest(unittest.TestCase):
    def _cfg(self):
        class Cfg:
            check_size = 50
            max_send_per_check = 15
            admin_user_id = 42
            check_interval = 1

        return Cfg()

    def _storage(self, tmp_root: str) -> Storage:
        return Storage(Path(tmp_root) / "state.json")

    def _target(self, tmp_file: str, baseline: bool) -> WatchTarget:
        return WatchTarget(
            target_id=1,
            url="https://www.kufar.by/l/x",
            label="раздел",
            params={"cat": "5"},
            enabled=True,
            baseline_established=baseline,
        )

    def test_baseline_then_new_detection(self):
        import asyncio

        from bot.handlers import BotContext
        from main import poll_once

        ad1 = models.ad_from_json(SAMPLE_AD)
        ad2 = models.ad_from_json({**SAMPLE_AD, "list_id": 1082357727, "subject": "Новое объявление"})
        ads = [ad1]

        with tempfile.TemporaryDirectory() as tmp:
            storage = self._storage(tmp)
            storage.save_targets({1: self._target(tmp, baseline=False)})
            client = FakeClient(ads)
            bot = FakeBot()
            ctx = BotContext(admin_id=7, storage=storage, client=client)
            cfg = self._cfg()

            # первый проход — baseline, ничего не отправляем
            asyncio.run(poll_once(bot, ctx, cfg))
            self.assertEqual(bot.sent, [])
            self.assertEqual(storage.load_seen(), {ad1.list_id})
            self.assertTrue(storage.load_targets()[1].baseline_established)

            # второй проход: то же + новое — шлём только новое
            ads.append(ad2)
            asyncio.run(poll_once(bot, ctx, cfg))
            self.assertEqual(len(bot.sent), 1)
            kind, _, caption = bot.sent[0]
            self.assertEqual(kind, "photo")
            self.assertIn("Новое объявление", caption)
            self.assertEqual(storage.load_seen(), {1082357726, 1082357727})


if __name__ == "__main__":
    unittest.main()