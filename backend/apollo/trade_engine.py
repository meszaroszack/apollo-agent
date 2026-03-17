"""
TradeEngine — Orchestrates the full alpha-to-execution pipeline.

Flow for each market tick:
    1. AlphaEngine → compute MatchupSignal (P_true vs P_market)
    2. SentimentGuardrail → optionally abort on negative news
    3. KellySizer → compute position size
    4. ReconciliationManager.trading_halted check
    5. KalshiClient.create_order → submit order
    6. LedgerEngine.record_fill → journal entry
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .alpha_engine import AlphaEngine, MatchupSignal
from .kalshi_client import KalshiClient, KalshiAPIError
from .kelly import KellySizer, SizingResult
from .reconciliation import LedgerEngine, ReconciliationManager
from .sentiment import SentimentGuardrail, SentimentResult

log = logging.getLogger("apollo.trade_engine")


@dataclass
class TradeDecision:
    matchup_signal: MatchupSignal
    sentiment_result: Optional[SentimentResult]
    sizing: SizingResult
    executed: bool
    order_id: Optional[str]
    abort_reason: Optional[str]
    timestamp: str


class TradeEngine:
    """
    Full trading pipeline — from market data to order submission.

    Parameters
    ----------
    alpha_engine : AlphaEngine
    sentiment_guardrail : SentimentGuardrail
    sizer : KellySizer
    kalshi_client : KalshiClient
    ledger : LedgerEngine
    recon_manager : ReconciliationManager
    dry_run : bool  — if True, log but never submit orders
    """

    def __init__(
        self,
        alpha_engine: AlphaEngine,
        sentiment_guardrail: SentimentGuardrail,
        sizer: KellySizer,
        kalshi_client: KalshiClient,
        ledger: LedgerEngine,
        recon_manager: ReconciliationManager,
        dry_run: bool = False,
    ):
        self._alpha = alpha_engine
        self._sentiment = sentiment_guardrail
        self._sizer = sizer
        self._kalshi = kalshi_client
        self._ledger = ledger
        self._recon = recon_manager
        self._dry_run = dry_run
        self.decision_log: list[TradeDecision] = []

    async def evaluate_and_trade(
        self,
        market_ticker: str,
        team_a_id: int,
        team_a_name: str,
        team_b_id: int,
        team_b_name: str,
        p_market_a: float,
    ) -> TradeDecision:
        """
        Full pipeline for a single matchup.
        """
        ts = datetime.now(timezone.utc).isoformat()

        # ── Step 1: Trading halt check ──────────────────────────────────
        if self._recon.trading_halted:
            decision = TradeDecision(
                matchup_signal=None, sentiment_result=None,
                sizing=None, executed=False, order_id=None,
                abort_reason="TRADING_HALTED: Reconciliation failure",
                timestamp=ts,
            )
            self.decision_log.append(decision)
            return decision

        # ── Step 2: Alpha signal ────────────────────────────────────────
        signal = await self._alpha.analyze_matchup(
            team_a_id, team_a_name, team_b_id, team_b_name, p_market_a
        )
        log.info("Signal: %s", signal.rationale)

        if signal.signal == "NEUTRAL":
            decision = TradeDecision(
                matchup_signal=signal, sentiment_result=None,
                sizing=None, executed=False, order_id=None,
                abort_reason="NEUTRAL: No exploitable divergence",
                timestamp=ts,
            )
            self.decision_log.append(decision)
            return decision

        # Determine which team to trade on
        trade_on_a = signal.signal in ("NO_A", "YES_A")
        primary_team = team_a_name if trade_on_a else team_b_name
        p_true = signal.p_true_a if trade_on_a else signal.p_true_b
        p_market = p_market_a if trade_on_a else (1.0 - p_market_a)
        side = "NO" if signal.signal in ("NO_A", "NO_B") else "YES"

        # ── Step 3: Sentiment guardrail ─────────────────────────────────
        sentiment = None
        if self._sentiment.is_enabled:
            sentiment = await self._sentiment.evaluate(team_a_name, team_b_name, primary_team)
            if sentiment.should_abort:
                decision = TradeDecision(
                    matchup_signal=signal, sentiment_result=sentiment,
                    sizing=None, executed=False, order_id=None,
                    abort_reason=f"SENTIMENT_ABORT: {sentiment.reason}",
                    timestamp=ts,
                )
                self.decision_log.append(decision)
                return decision

        # ── Step 4: Kelly sizing ────────────────────────────────────────
        sizing = self._sizer.screen_no_side(p_true, p_market) if side == "NO" else \
                 self._sizer.size(p_true, p_market, side="YES")

        if not sizing.should_trade:
            decision = TradeDecision(
                matchup_signal=signal, sentiment_result=sentiment,
                sizing=sizing, executed=False, order_id=None,
                abort_reason=f"KELLY_SKIP: {sizing.rationale}",
                timestamp=ts,
            )
            self.decision_log.append(decision)
            return decision

        # ── Step 5: Execute order ───────────────────────────────────────
        order_id = None
        executed = False

        if self._dry_run:
            log.info(
                "[DRY RUN] Would %s %s on %s — %d contracts @ ~%d¢",
                side, market_ticker, primary_team,
                sizing.position_cents // 100,
                int(p_market * 100),
            )
            executed = True
            order_id = f"DRYRUN-{uuid.uuid4().hex[:8].upper()}"
        else:
            try:
                # Convert dollar size → number of contracts
                # Each Kalshi contract trades at yes_price cents (max $1)
                price_cents = int(p_market * 100)
                n_contracts = max(1, sizing.position_cents // 100)
                kalshi_side = "no" if side == "NO" else "yes"
                kalshi_action = "buy"

                response = await self._kalshi.create_order(
                    ticker=market_ticker,
                    action=kalshi_action,
                    side=kalshi_side,
                    order_type="limit",
                    count=n_contracts,
                    price=price_cents,
                    client_order_id=f"apollo-{uuid.uuid4().hex[:12]}",
                )
                order_id = response.get("order", {}).get("order_id")
                executed = True

                # Record fill in ledger
                await self._ledger.record_fill(
                    fill_id=order_id,
                    amount_cents=sizing.position_cents,
                    description=f"{side} {n_contracts}x {market_ticker} @ {price_cents}¢",
                )
                log.info("Order placed: %s | order_id=%s", sizing.rationale, order_id)

            except KalshiAPIError as exc:
                log.error("Order submission failed: %s", exc)
                executed = False
                order_id = None

        decision = TradeDecision(
            matchup_signal=signal,
            sentiment_result=sentiment,
            sizing=sizing,
            executed=executed,
            order_id=order_id,
            abort_reason=None,
            timestamp=ts,
        )
        self.decision_log.append(decision)
        return decision

    def recent_decisions(self, n: int = 50) -> list[dict]:
        """Return last N decisions as serializable dicts."""
        results = []
        for d in self.decision_log[-n:]:
            results.append({
                "timestamp": d.timestamp,
                "executed": d.executed,
                "order_id": d.order_id,
                "abort_reason": d.abort_reason,
                "signal": d.matchup_signal.signal if d.matchup_signal else None,
                "edge": d.matchup_signal.edge if d.matchup_signal else None,
                "rationale": d.matchup_signal.rationale if d.matchup_signal else None,
                "sizing_rationale": d.sizing.rationale if d.sizing else None,
                "sentiment_score": d.sentiment_result.score if d.sentiment_result else None,
                "p_true": d.sizing.p_true if d.sizing else None,
                "p_market": d.sizing.p_market if d.sizing else None,
                "position_dollars": d.sizing.position_dollars if d.sizing else None,
            })
        return results
