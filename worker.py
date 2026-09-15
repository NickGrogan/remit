"""
REMIT Insider — Worker Thread
Polls the Elexon REMIT API every 60 seconds and builds an in-memory alert store.
"""

import threading
import time
import logging
from collections import deque
from datetime import datetime, timedelta, timezone

import requests

from logic import parse_alert

logger = logging.getLogger("remit.worker")

API_BASE = "https://data.elexon.co.uk/bmrs/api/v1"
POLL_INTERVAL = 60          # seconds
MAX_ALERTS = 300            # rolling buffer size
INITIAL_LOOKBACK_HOURS = 48 # how far back to look on first poll


class RemitWorker:
    """Background worker that polls Elexon REMIT and maintains an alert store."""

    def __init__(self):
        self.alerts: deque = deque(maxlen=MAX_ALERTS)
        self._seen: set = set()       # (mrid, revision) tuples
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_poll: datetime | None = None
        self._stats = {
            "total_mw_offline": 0.0,
            "active_outages": 0,
            "flash_count": 0,
            "last_poll": None,
            "poll_status": "starting",
            "messages_fetched": 0,
        }

    # ── Public API ──────────────────────────────────

    def start(self):
        """Start the background polling thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="remit-worker")
        self._thread.start()
        logger.info("Worker thread started")

    def stop(self):
        """Signal the worker to stop."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Worker thread stopped")

    def get_alerts(self, limit: int = 100) -> list[dict]:
        """Return the latest alerts, newest first."""
        with self._lock:
            items = list(self.alerts)
        # newest first
        items.sort(key=lambda a: a.get("published", ""), reverse=True)
        return items[:limit]

    def get_stats(self) -> dict:
        """Return summary statistics."""
        with self._lock:
            return dict(self._stats)

    # ── Internal ────────────────────────────────────

    def _run(self):
        """Main polling loop."""
        # Initial fetch: look back further
        self._poll(lookback_hours=INITIAL_LOOKBACK_HOURS)

        while not self._stop_event.is_set():
            self._stop_event.wait(POLL_INTERVAL)
            if self._stop_event.is_set():
                break
            self._poll(lookback_hours=0.1)  # ~6 min overlap for safety

    def _poll(self, lookback_hours: float = 0.1):
        """Fetch new REMIT messages from Elexon."""
        now = datetime.now(timezone.utc)

        if self._last_poll:
            from_dt = self._last_poll - timedelta(minutes=5)  # overlap for safety
        else:
            from_dt = now - timedelta(hours=lookback_hours)

        params = {
            "from": from_dt.strftime("%Y/%m/%d %H:%M"),
            "to": now.strftime("%Y/%m/%d %H:%M"),
            "format": "json",
            "latestRevisionOnly": "true",
        }

        try:
            logger.info(f"Polling REMIT: {params['from']} → {params['to']}")
            resp = requests.get(
                f"{API_BASE}/remit/list/by-publish",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            listing = resp.json().get("data", [])
            logger.info(f"Got {len(listing)} message references")

            new_count = 0
            for item in listing:
                msg_id = item.get("id")
                mrid = item.get("mrid", "")
                rev = item.get("revisionNumber", 0)
                key = (mrid, rev)

                if key in self._seen:
                    continue

                # Fetch full message detail
                detail = self._fetch_detail(msg_id)
                if detail:
                    alert = parse_alert(detail)
                    with self._lock:
                        self.alerts.append(alert)
                        self._seen.add(key)
                    new_count += 1

            self._last_poll = now
            self._update_stats(new_count)
            logger.info(f"Processed {new_count} new alerts (total: {len(self.alerts)})")

        except requests.RequestException as e:
            logger.error(f"Poll failed: {e}")
            with self._lock:
                self._stats["poll_status"] = f"error: {e}"

    def _fetch_detail(self, message_id: int) -> dict | None:
        """Fetch full REMIT message by ID."""
        try:
            resp = requests.get(
                f"{API_BASE}/remit/{message_id}",
                params={"format": "json"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if data:
                return data[0]
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch detail for {message_id}: {e}")
        return None

    def _update_stats(self, new_count: int):
        """Recalculate summary stats from the current alert store."""
        with self._lock:
            alerts = list(self.alerts)
            active = [a for a in alerts if a["event_type"] in ("TRIP", "OUTAGE", "REDUCED")]
            self._stats.update({
                "total_mw_offline": sum(a["impact_mw"] for a in active),
                "active_outages": len(active),
                "flash_count": sum(1 for a in alerts if a["severity"] == "FLASH"),
                "last_poll": datetime.now(timezone.utc).isoformat(),
                "poll_status": "ok",
                "messages_fetched": self._stats.get("messages_fetched", 0) + new_count,
            })
