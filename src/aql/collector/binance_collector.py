"""
AQL Binance Collector — G1-WP01-MVP

WebSocket kline stream for Binance Spot public market data.
No API keys required (public endpoint).

Pipeline:
  Binance WebSocket → DurableJournal.commit() → OperationalStore.upsert()

Telemetry tracked per execution order §A:
  - source timestamps (Binance k.t / k.T)
  - local ingested_at (wall-clock on message receipt)
  - committed_at (after journal fsync)
  - ws_message_count, final_bar_count, duplicate_count, error_count
"""
from __future__ import annotations

import json
import logging
import ssl
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

import websocket  # websocket-client

from ..journal.durable_journal import DurableJournal
from ..models.bar import BarState, MarketBar
from ..storage.operational_store import OperationalStore

logger = logging.getLogger(__name__)

# Binance WebSocket stream URL (public, no auth)
WS_BASE = "wss://stream.binance.com:9443/ws"

# Reconnect config
MAX_RECONNECT_ATTEMPTS = 10
RECONNECT_BACKOFF_S = [1, 2, 4, 8, 16, 30, 30, 30, 30, 30]


@dataclass
class CollectorMetrics:
    ws_message_count: int = 0
    final_bar_count: int = 0
    non_final_bar_count: int = 0
    duplicate_count: int = 0
    journal_commit_count: int = 0
    store_insert_count: int = 0
    error_count: int = 0
    reconnect_count: int = 0
    last_bar_open: Optional[int] = None
    last_ingested_at: Optional[int] = None
    last_committed_at: Optional[int] = None
    first_connect_at: Optional[int] = None
    disconnect_at: Optional[int] = None
    # Latency tracking (ms)
    latency_ws_to_commit_samples: list = field(default_factory=list)

    def avg_latency_ws_to_commit_ms(self) -> Optional[float]:
        if not self.latency_ws_to_commit_samples:
            return None
        return sum(self.latency_ws_to_commit_samples) / len(self.latency_ws_to_commit_samples)


class BinanceCollector:
    """
    Streams BTCUSDT 1m klines from Binance WebSocket.
    - Distinguishes final vs non-final bars (k.x field).
    - Commits final bars to DurableJournal (fsync boundary).
    - Upserts from journal to OperationalStore (idempotent).
    - Records all temporal fields per TIME-01.
    - Tracks gap window on disconnect for gap recovery.
    """

    def __init__(
        self,
        symbol: str,
        interval: str,
        journal: DurableJournal,
        store: OperationalStore,
        max_bars: Optional[int] = None,
    ):
        self.symbol = symbol.upper()
        self.interval = interval
        self.journal = journal
        self.store = store
        self.max_bars = max_bars
        self.metrics = CollectorMetrics()
        self._stop_event = threading.Event()
        self._ws: Optional[websocket.WebSocketApp] = None
        # Track disconnect window for gap recovery
        self.gap_start_ms: Optional[int] = None
        self.gap_end_ms: Optional[int] = None

    def _stream_name(self) -> str:
        return f"{self.symbol.lower()}@kline_{self.interval}"

    def _on_message(self, ws, message: str) -> None:
        try:
            self.metrics.ws_message_count += 1
            data = json.loads(message)

            if "k" not in data:
                return

            k = data["k"]
            bar = MarketBar.from_binance_ws_kline(k)

            if not bar.is_final:
                self.metrics.non_final_bar_count += 1
                return

            self.metrics.final_bar_count += 1
            self.metrics.last_bar_open = bar.bar_open
            self.metrics.last_ingested_at = bar.ingested_at

            # Commit to journal (fsync boundary)
            committed = self.journal.commit(bar)
            if committed:
                self.metrics.journal_commit_count += 1
                committed_at = bar.committed_at
                self.metrics.last_committed_at = committed_at

                # Latency: ingested_at → committed_at
                if committed_at and bar.ingested_at:
                    lat = committed_at - bar.ingested_at
                    self.metrics.latency_ws_to_commit_samples.append(lat)
                    if len(self.metrics.latency_ws_to_commit_samples) > 1000:
                        self.metrics.latency_ws_to_commit_samples = \
                            self.metrics.latency_ws_to_commit_samples[-500:]
            else:
                self.metrics.duplicate_count += 1

            # Upsert to operational store (idempotent)
            if self.store.upsert(bar):
                self.metrics.store_insert_count += 1
                self.journal.mark_persisted(bar.stable_key())

            if self.max_bars and self.metrics.journal_commit_count >= self.max_bars:
                logger.info("Reached max_bars=%d, stopping.", self.max_bars)
                self._stop_event.set()
                ws.close()

        except Exception as exc:
            self.metrics.error_count += 1
            logger.error("on_message error: %s", exc, exc_info=True)

    def _on_error(self, ws, error) -> None:
        self.metrics.error_count += 1
        logger.warning("WebSocket error: %s", error)

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        self.metrics.disconnect_at = int(time.time() * 1000)
        if self.metrics.last_bar_open:
            self.gap_start_ms = self.metrics.last_bar_open
        logger.info(
            "WebSocket closed: code=%s msg=%s gap_start=%s",
            close_status_code, close_msg, self.gap_start_ms,
        )

    def _on_open(self, ws) -> None:
        if self.metrics.first_connect_at is None:
            self.metrics.first_connect_at = int(time.time() * 1000)
        # Record gap end when we reconnect (gap window now closed)
        if self.gap_start_ms is not None:
            self.gap_end_ms = int(time.time() * 1000)
            logger.info(
                "Reconnected. Gap window: %d → %d (%d ms)",
                self.gap_start_ms,
                self.gap_end_ms,
                self.gap_end_ms - self.gap_start_ms,
            )
        logger.info("WebSocket connected: %s", self._stream_name())

    def run(self, timeout_s: Optional[float] = None) -> CollectorMetrics:
        """
        Run the collector synchronously.  Returns metrics on completion.
        timeout_s: stop after this many seconds (useful for tests / 10-min run).
        """
        url = f"{WS_BASE}/{self._stream_name()}"
        self._stop_event.clear()

        def _run_ws():
            attempt = 0
            while not self._stop_event.is_set():
                try:
                    ws = websocket.WebSocketApp(
                        url,
                        on_message=self._on_message,
                        on_error=self._on_error,
                        on_close=self._on_close,
                        on_open=self._on_open,
                    )
                    self._ws = ws
                    ws.run_forever(
                        sslopt={"cert_reqs": ssl.CERT_REQUIRED},
                        ping_interval=20,
                        ping_timeout=10,
                    )
                except Exception as exc:
                    logger.error("WS run_forever raised: %s", exc)

                if self._stop_event.is_set():
                    break

                attempt += 1
                if attempt >= MAX_RECONNECT_ATTEMPTS:
                    logger.error("Max reconnect attempts reached.")
                    break

                backoff = RECONNECT_BACKOFF_S[min(attempt - 1, len(RECONNECT_BACKOFF_S) - 1)]
                logger.info("Reconnecting in %ds (attempt %d)...", backoff, attempt)
                self.metrics.reconnect_count += 1
                time.sleep(backoff)

        t = threading.Thread(target=_run_ws, daemon=True)
        t.start()

        deadline = time.time() + timeout_s if timeout_s else None
        try:
            while t.is_alive():
                if self._stop_event.is_set():
                    break
                if deadline and time.time() >= deadline:
                    logger.info("Timeout reached, stopping collector.")
                    self._stop_event.set()
                    if self._ws:
                        self._ws.close()
                    break
                time.sleep(0.5)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt, stopping.")
            self._stop_event.set()
            if self._ws:
                self._ws.close()

        t.join(timeout=5)
        return self.metrics

    def stop(self) -> None:
        self._stop_event.set()
        if self._ws:
            self._ws.close()
