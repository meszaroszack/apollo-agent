"""
OrderbookManager — Real-time local orderbook via Kalshi WebSocket.

Subscribes to the orderbook_delta channel and maintains a local bid/ask book.
Uses asyncio + websockets for low-latency event processing.
"""

import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Callable, Optional
from urllib.parse import urlencode

import websockets
from websockets.exceptions import ConnectionClosed

from .signer import KalshiSigner

log = logging.getLogger("apollo.orderbook")

KALSHI_WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
RECONNECT_DELAY_SECONDS = 2
MAX_RECONNECT_ATTEMPTS = 10


class OrderbookLevel:
    __slots__ = ("price", "quantity")

    def __init__(self, price: int, quantity: int):
        self.price = price       # cents (0–100)
        self.quantity = quantity # number of contracts


class LocalOrderbook:
    """Thread-safe local orderbook snapshot for a single market."""

    def __init__(self, market_ticker: str):
        self.market_ticker = market_ticker
        self.yes_bids: dict[int, int] = {}   # price → quantity
        self.yes_asks: dict[int, int] = {}
        self.no_bids: dict[int, int] = {}
        self.no_asks: dict[int, int] = {}
        self.last_updated: float = 0.0
        self._lock = asyncio.Lock()

    async def apply_delta(self, delta: dict) -> None:
        """Apply an orderbook_delta event to the local book."""
        async with self._lock:
            side = delta.get("side", "yes")
            price = int(delta.get("price", 0))
            qty = int(delta.get("delta", 0))

            if side == "yes":
                bid_book = self.yes_bids
                ask_book = self.yes_asks
            else:
                bid_book = self.no_bids
                ask_book = self.no_asks

            # delta > 0 → add to bids, delta < 0 → bids reduce, asks grow
            if qty > 0:
                bid_book[price] = bid_book.get(price, 0) + qty
                if bid_book[price] <= 0:
                    bid_book.pop(price, None)
            elif qty < 0:
                ask_book[price] = ask_book.get(price, 0) + abs(qty)
                if ask_book[price] <= 0:
                    ask_book.pop(price, None)

            self.last_updated = time.time()

    def best_yes_bid(self) -> Optional[int]:
        """Highest price someone will buy YES at."""
        return max(self.yes_bids.keys()) if self.yes_bids else None

    def best_yes_ask(self) -> Optional[int]:
        """Lowest price someone will sell YES at."""
        return min(self.yes_asks.keys()) if self.yes_asks else None

    def mid_price(self) -> Optional[float]:
        bid = self.best_yes_bid()
        ask = self.best_yes_ask()
        if bid is not None and ask is not None:
            return (bid + ask) / 2.0
        return bid or ask

    def spread(self) -> Optional[int]:
        bid = self.best_yes_bid()
        ask = self.best_yes_ask()
        if bid is not None and ask is not None:
            return ask - bid
        return None

    def to_dict(self) -> dict:
        return {
            "ticker": self.market_ticker,
            "yes_bids": dict(sorted(self.yes_bids.items(), reverse=True)[:5]),
            "yes_asks": dict(sorted(self.yes_asks.items())[:5]),
            "no_bids": dict(sorted(self.no_bids.items(), reverse=True)[:5]),
            "no_asks": dict(sorted(self.no_asks.items())[:5]),
            "best_yes_bid": self.best_yes_bid(),
            "best_yes_ask": self.best_yes_ask(),
            "mid_price": self.mid_price(),
            "spread": self.spread(),
            "last_updated": self.last_updated,
        }


class OrderbookManager:
    """
    Manages WebSocket connection to Kalshi and maintains local orderbooks
    for subscribed markets.

    Usage
    -----
    mgr = OrderbookManager(signer, ["NCAAB-2026-DUKE", "NCAAB-2026-UNC"])
    await mgr.start()
    book = mgr.get_book("NCAAB-2026-DUKE")
    """

    def __init__(
        self,
        signer: KalshiSigner,
        market_tickers: list[str],
        on_update: Optional[Callable[[str, dict], None]] = None,
    ):
        self._signer = signer
        self._tickers = market_tickers
        self._on_update = on_update
        self._books: dict[str, LocalOrderbook] = {
            t: LocalOrderbook(t) for t in market_tickers
        }
        self._ws_task: Optional[asyncio.Task] = None
        self._running = False
        self._reconnect_count = 0

    def get_book(self, ticker: str) -> Optional[LocalOrderbook]:
        return self._books.get(ticker)

    def all_books(self) -> dict[str, dict]:
        return {t: b.to_dict() for t, b in self._books.items()}

    async def start(self) -> None:
        self._running = True
        self._ws_task = asyncio.create_task(self._connect_loop())

    async def stop(self) -> None:
        self._running = False
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

    def subscribe(self, ticker: str) -> None:
        """Add a new ticker to watch (will subscribe on next reconnect)."""
        if ticker not in self._books:
            self._books[ticker] = LocalOrderbook(ticker)
            self._tickers.append(ticker)

    # ------------------------------------------------------------------
    # WebSocket connection loop
    # ------------------------------------------------------------------

    async def _connect_loop(self) -> None:
        while self._running and self._reconnect_count < MAX_RECONNECT_ATTEMPTS:
            try:
                await self._connect_and_stream()
                self._reconnect_count = 0  # reset on clean disconnect
            except ConnectionClosed as e:
                log.warning("WebSocket closed: %s — reconnecting in %ds", e, RECONNECT_DELAY_SECONDS)
            except Exception as e:
                log.error("WebSocket error: %s — reconnecting in %ds", e, RECONNECT_DELAY_SECONDS)

            if self._running:
                self._reconnect_count += 1
                await asyncio.sleep(RECONNECT_DELAY_SECONDS * self._reconnect_count)

        if self._reconnect_count >= MAX_RECONNECT_ATTEMPTS:
            log.critical("Max WebSocket reconnect attempts reached — orderbook stream DEAD")

    async def _connect_and_stream(self) -> None:
        auth_params = self._signer.websocket_auth_params()
        ws_url = f"{KALSHI_WS_URL}?{urlencode(auth_params)}"

        async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10) as ws:
            log.info("WebSocket connected to Kalshi")
            await self._subscribe(ws)

            async for raw in ws:
                await self._handle_message(raw)

    async def _subscribe(self, ws) -> None:
        sub_msg = {
            "id": 1,
            "cmd": "subscribe",
            "params": {
                "channels": ["orderbook_delta"],
                "market_tickers": self._tickers,
            },
        }
        await ws.send(json.dumps(sub_msg))
        log.info("Subscribed to orderbook_delta for %d markets", len(self._tickers))

    async def _handle_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Invalid JSON from WS: %s", raw[:100])
            return

        msg_type = msg.get("type")

        if msg_type == "orderbook_delta":
            ticker = msg.get("market_ticker", "")
            book = self._books.get(ticker)
            if book:
                await book.apply_delta(msg)
                if self._on_update:
                    self._on_update(ticker, book.to_dict())

        elif msg_type == "subscribed":
            log.info("Subscription confirmed: %s", msg)

        elif msg_type == "error":
            log.error("WS server error: %s", msg)
