"""
KalshiClient — Async REST client for the Kalshi trading API.
All requests are signed via KalshiSigner.
"""

import logging
from typing import Any, Optional

import httpx

from .signer import KalshiSigner

log = logging.getLogger("apollo.kalshi_client")

KALSHI_BASE = "https://trading-api.kalshi.com"
API_PREFIX = "/trade-api/v2"


class KalshiAPIError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"Kalshi API {status}: {message}")
        self.status = status


class KalshiClient:
    """
    Thin async wrapper around Kalshi's REST API.
    Every private endpoint is signed with RSA-PSS via KalshiSigner.
    """

    def __init__(self, signer: KalshiSigner):
        self._signer = signer
        self._http = httpx.AsyncClient(
            base_url=KALSHI_BASE,
            timeout=10,
            follow_redirects=True,
        )

    async def close(self):
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Portfolio
    # ------------------------------------------------------------------

    async def get_balance(self) -> dict:
        return await self._get(f"{API_PREFIX}/portfolio/balance")

    async def get_positions(self, ticker: Optional[str] = None) -> dict:
        params = {}
        if ticker:
            params["ticker"] = ticker
        return await self._get(f"{API_PREFIX}/portfolio/positions", params=params)

    async def get_fills(self, ticker: Optional[str] = None, limit: int = 100) -> dict:
        params = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        return await self._get(f"{API_PREFIX}/portfolio/fills", params=params)

    # ------------------------------------------------------------------
    # Markets
    # ------------------------------------------------------------------

    async def get_markets(
        self,
        event_ticker: Optional[str] = None,
        status: str = "open",
        limit: int = 100,
    ) -> dict:
        params = {"status": status, "limit": limit}
        if event_ticker:
            params["event_ticker"] = event_ticker
        return await self._get(f"{API_PREFIX}/markets", params=params)

    async def get_market(self, ticker: str) -> dict:
        return await self._get(f"{API_PREFIX}/markets/{ticker}")

    async def get_orderbook(self, ticker: str, depth: int = 10) -> dict:
        return await self._get(
            f"{API_PREFIX}/markets/{ticker}/orderbook",
            params={"depth": depth},
        )

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    async def create_order(
        self,
        ticker: str,
        action: str,         # "buy" or "sell"
        side: str,           # "yes" or "no"
        order_type: str,     # "limit" or "market"
        count: int,          # number of contracts
        price: Optional[int] = None,  # cents (required for limit)
        client_order_id: Optional[str] = None,
    ) -> dict:
        """
        Place an order on Kalshi.

        Parameters
        ----------
        ticker : str       Market ticker (e.g. "NCAAB-2026-DUKE")
        action : str       "buy" or "sell"
        side : str         "yes" or "no"
        order_type : str   "limit" or "market"
        count : int        Number of contracts (min 1)
        price : int        Limit price in cents (1–99), required for limit orders
        """
        body: dict[str, Any] = {
            "ticker": ticker,
            "action": action.lower(),
            "side": side.lower(),
            "type": order_type.lower(),
            "count": count,
        }
        if price is not None:
            body["yes_price"] = price
        if client_order_id:
            body["client_order_id"] = client_order_id

        return await self._post(f"{API_PREFIX}/portfolio/orders", body)

    async def cancel_order(self, order_id: str) -> dict:
        return await self._delete(f"{API_PREFIX}/portfolio/orders/{order_id}")

    async def get_order(self, order_id: str) -> dict:
        return await self._get(f"{API_PREFIX}/portfolio/orders/{order_id}")

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def get_events(self, status: str = "open", limit: int = 100) -> dict:
        return await self._get(
            f"{API_PREFIX}/events", params={"status": status, "limit": limit}
        )

    async def get_event(self, event_ticker: str) -> dict:
        return await self._get(f"{API_PREFIX}/events/{event_ticker}")

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        headers = self._signer.build_auth_headers("GET", path)
        resp = await self._http.get(path, headers=headers, params=params)
        return self._handle(resp)

    async def _post(self, path: str, body: dict) -> dict:
        headers = self._signer.build_auth_headers("POST", path)
        resp = await self._http.post(path, headers=headers, json=body)
        return self._handle(resp)

    async def _delete(self, path: str) -> dict:
        headers = self._signer.build_auth_headers("DELETE", path)
        resp = await self._http.delete(path, headers=headers)
        return self._handle(resp)

    @staticmethod
    def _handle(resp: httpx.Response) -> dict:
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("message", resp.text)
            except Exception:
                detail = resp.text
            raise KalshiAPIError(resp.status_code, detail)
        return resp.json() if resp.content else {}
