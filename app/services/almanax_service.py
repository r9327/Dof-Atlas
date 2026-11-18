"""Sourced Almanax Dofus 3 data, asynchronous Qt requests and offline cache."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from time import time
from typing import Any

from PySide6.QtCore import QObject, QStandardPaths, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from app.constants import CONFIG_DIR
from app.core.json_store import read_json_resilient, write_json_atomic

LOGGER = logging.getLogger(__name__)
API_BASE = "https://api.dofusdu.de/dofus3/v1/fr/almanax/"
CACHE_TTL_SECONDS = 6 * 3600
MAX_CACHE_DAYS = 90


@dataclass(frozen=True, slots=True)
class AlmanaxDay:
    date: str
    offering: str
    quantity: int
    bonus: str
    bonus_type: str
    reward_kamas: int = 0
    item_icon_url: str = ""


def parse_almanax_day(value: Any, expected_date: str) -> AlmanaxDay | None:
    """Parse the documented Dofusdude schema, never fabricate absent fields."""
    if not isinstance(value, dict) or value.get("date") != expected_date:
        return None
    try:
        if date.fromisoformat(expected_date).isoformat() != expected_date:
            return None
    except (TypeError, ValueError):
        return None
    tribute = value.get("tribute")
    tribute = tribute if isinstance(tribute, dict) else {}
    item = tribute.get("item")
    item = item if isinstance(item, dict) else {}
    offering = str(item.get("name") or "").strip()[:160]
    try:
        quantity = int(tribute.get("quantity") or 0)
    except (TypeError, ValueError, OverflowError):
        quantity = 0
    if not offering or not 1 <= quantity <= 100000:
        offering, quantity = "", 0
    bonus = value.get("bonus")
    bonus = bonus if isinstance(bonus, dict) else {}
    description = str(bonus.get("description") or "").strip()[:1200]
    category = bonus.get("type")
    category = category if isinstance(category, dict) else {}
    kind = str(category.get("name") or "").strip()[:160]
    if not offering and not description:
        return None
    try:
        reward = int(value.get("reward_kamas") or 0)
    except (TypeError, ValueError, OverflowError):
        reward = 0
    if not 0 <= reward <= 2_000_000_000:
        reward = 0
    image_urls = item.get("image_urls")
    image_urls = image_urls if isinstance(image_urls, dict) else {}
    icon_url = str(image_urls.get("icon") or "")
    if not (
        icon_url.startswith("https://api.dofusdu.de/dofus3/v1/img/item/")
        and icon_url.endswith(".png")
    ):
        icon_url = ""
    return AlmanaxDay(
        expected_date, offering, quantity, description, kind,
        reward_kamas=reward, item_icon_url=icon_url,
    )


def _cached_payload(day: AlmanaxDay) -> dict[str, Any]:
    return {
        "date": day.date,
        "tribute": {
            "item": {
                "name": day.offering,
                "image_urls": {"icon": day.item_icon_url},
            },
            "quantity": day.quantity,
        },
        "reward_kamas": day.reward_kamas,
        "bonus": {
            "description": day.bonus,
            "type": {"name": day.bonus_type},
        },
    }


class AlmanaxDataService(QObject):
    """One owner for Home and calendar; HTTP never blocks the Qt event loop.

    dayAvailable(date, day, cached) and dayUnavailable(date, reason).
    Dates are exact ISO days; response data is never reattributed to another
    day. An unavailable network does not discard a previously cached day.
    """

    dayAvailable = Signal(str, object, bool)
    dayUnavailable = Signal(str, str)
    itemIconAvailable = Signal(str, object)

    def __init__(self, parent: QObject | None = None, *, cache_path: Path | None = None):
        super().__init__(parent)
        cache_root = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.CacheLocation
        )
        self.cache_path = Path(cache_path) if cache_path is not None else (
            (Path(cache_root) if cache_root else CONFIG_DIR / "cache")
            / "almanax_dofus3_fr_v1.json"
        )
        self._network = QNetworkAccessManager(self)
        self._cache: dict[str, tuple[AlmanaxDay, float]] = {}
        self._pending: dict[str, QNetworkReply] = {}
        self._icon_cache: dict[str, QPixmap] = {}
        self._icon_pending: dict[str, tuple[QNetworkReply, set[str]]] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        data = read_json_resilient(self.cache_path, {"days": {}})
        records = data.get("days") if isinstance(data, dict) else None
        if not isinstance(records, dict):
            return
        # Disk order is not freshness: older files may have more than the
        # bounded 90 days in an arbitrary JSON key order. Validate first, then
        # retain the newest successful fetches.
        candidates: list[tuple[str, AlmanaxDay, float]] = []
        latest_allowed = time() + 60
        for key, record in records.items():
            if not isinstance(key, str) or not isinstance(record, dict):
                continue
            day = parse_almanax_day(record.get("payload"), key)
            saved = record.get("fetched_at")
            if day is None or not isinstance(saved, (int, float)):
                continue
            if 0 < saved <= latest_allowed:
                candidates.append((key, day, float(saved)))
        for key, day, saved in sorted(
            candidates, key=lambda entry: entry[2], reverse=True
        )[:MAX_CACHE_DAYS]:
            self._cache[key] = (day, saved)

    def _persist_cache(self) -> None:
        recent = sorted(
            self._cache.items(), key=lambda row: row[1][1], reverse=True
        )[:MAX_CACHE_DAYS]
        # The cap applies to RAM as well as the on-disk JSON cache.
        self._cache = dict(recent)
        payload = {
            "version": 1,
            "days": {
                key: {
                    "fetched_at": timestamp,
                    "payload": _cached_payload(day),
                }
                for key, (day, timestamp) in recent
            },
        }
        try:
            write_json_atomic(self.cache_path, payload)
        except OSError:
            LOGGER.warning("Almanax cache not writable: %s", self.cache_path)

    def request_day(self, day_key: str, *, refresh: bool = False) -> bool:
        try:
            if date.fromisoformat(day_key).isoformat() != day_key:
                return False
        except (TypeError, ValueError):
            return False
        cached = self._cache.get(day_key)
        if cached is not None:
            self.dayAvailable.emit(day_key, cached[0], True)
            self._request_item_icon(cached[0])
            if not refresh and time() - cached[1] < CACHE_TTL_SECONDS:
                return True
        if day_key in self._pending:
            return True
        request = QNetworkRequest(QUrl(API_BASE + day_key))
        request.setRawHeader(b"Accept", b"application/json")
        request.setTransferTimeout(8000)
        reply = self._network.get(request)
        self._pending[day_key] = reply
        reply.finished.connect(
            lambda key=day_key, result=reply: self._finish_request(key, result)
        )
        return True

    def _finish_request(self, day_key: str, reply: QNetworkReply) -> None:
        if self._pending.get(day_key) is not reply:
            reply.deleteLater()
            return
        del self._pending[day_key]
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise ValueError("source unreachable")
            body = bytes(reply.readAll())
            if not 0 < len(body) <= 128 * 1024:
                raise ValueError("unexpected response size")
            day = parse_almanax_day(json.loads(body.decode("utf-8")), day_key)
            if day is None:
                raise ValueError("missing sourced offering and bonus")
        except (ValueError, UnicodeError) as exc:
            LOGGER.info("Almanax unavailable for %s: %s", day_key, exc)
            if day_key not in self._cache:
                self.dayUnavailable.emit(
                    day_key, "Source Almanax indisponible pour cette date."
                )
        else:
            self._cache[day_key] = (day, time())
            self._persist_cache()
            self.dayAvailable.emit(day_key, day, False)
            self._request_item_icon(day)
        finally:
            reply.deleteLater()

    def _request_item_icon(self, day: AlmanaxDay) -> None:
        """Load the documented offering image without blocking Qt."""

        url = day.item_icon_url
        if not url:
            return
        icon = self._icon_cache.get(url)
        if icon is not None:
            self.itemIconAvailable.emit(day.date, icon)
            return
        pending = self._icon_pending.get(url)
        if pending is not None:
            pending[1].add(day.date)
            return
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(8000)
        reply = self._network.get(request)
        self._icon_pending[url] = (reply, {day.date})
        reply.finished.connect(
            lambda target=url, result=reply: self._finish_item_icon(target, result)
        )

    def _finish_item_icon(self, url: str, reply: QNetworkReply) -> None:
        pending = self._icon_pending.get(url)
        try:
            if pending is None or pending[0] is not reply:
                return
            # An obsolete response must never drop a newer in-flight request
            # for the same icon URL.
            del self._icon_pending[url]
            if reply.error() != QNetworkReply.NetworkError.NoError:
                return
            body = bytes(reply.readAll())
            if not 0 < len(body) <= 256 * 1024:
                return
            icon = QPixmap()
            if not icon.loadFromData(body, "PNG") or icon.isNull():
                return
            if icon.width() > 256 or icon.height() > 256:
                return
            if len(self._icon_cache) >= 48:
                self._icon_cache.pop(next(iter(self._icon_cache)))
            self._icon_cache[url] = icon
            for key in sorted(pending[1]):
                self.itemIconAvailable.emit(key, icon)
        finally:
            reply.deleteLater()
