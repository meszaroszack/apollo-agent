"""
KellySizer — Quarter-Kelly position sizing for binary Kalshi event contracts.

Formula (binary Kelly):
    K* = ( p*(b+1) - 1 ) / b

Where:
    p = model-derived win probability (P_true)
    b = net payout ratio  (e.g. if contract pays $1 on a $0.60 stake → b = 0.667)

The system defaults to 0.25x (Quarter-Kelly) to limit portfolio drawdown.
Hard cap: 3% of total bankroll per contract.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN


KELLY_FRACTION = Decimal("0.25")   # Quarter-Kelly multiplier
MAX_POSITION_PCT = Decimal("0.03") # Hard cap: 3% of bankroll per contract
MIN_EDGE = Decimal("0.02")         # Minimum required edge before sizing (2%)


@dataclass
class SizingResult:
    p_true: float
    p_market: float
    edge: float
    kelly_full: float
    kelly_fractional: float
    position_dollars: float
    position_cents: int          # Kalshi uses integer cents
    bet_on: str                  # "NO" or "YES"
    rationale: str
    should_trade: bool


class KellySizer:
    """
    Computes optimal contract size for each trade signal.

    Parameters
    ----------
    bankroll : float
        Current total bankroll in USD.
    kelly_fraction : float
        Multiplier applied to full Kelly (default 0.25).
    max_position_pct : float
        Hard cap as fraction of bankroll (default 0.03 → 3%).
    """

    def __init__(
        self,
        bankroll: float,
        kelly_fraction: float = float(KELLY_FRACTION),
        max_position_pct: float = float(MAX_POSITION_PCT),
    ):
        self.bankroll = Decimal(str(bankroll))
        self.kelly_fraction = Decimal(str(kelly_fraction))
        self.max_position_pct = Decimal(str(max_position_pct))

    # ------------------------------------------------------------------
    # Core sizing method
    # ------------------------------------------------------------------

    def size(
        self,
        p_true: float,
        p_market: float,
        side: str = "NO",
    ) -> SizingResult:
        """
        Compute Quarter-Kelly size for a given contract.

        Parameters
        ----------
        p_true : float
            Model-derived probability that the "YES" outcome occurs (0–1).
        p_market : float
            Kalshi's current market price for "YES" (0–1, i.e. cents/100).
        side : str
            "NO" — we are selling YES (shorting the hype side)
            "YES" — we are buying YES because market underprices it
        """
        p = Decimal(str(p_true))
        pm = Decimal(str(p_market))

        # Determine effective probability from our perspective
        # For NO side: our win prob = 1 - p_true, payout = pm / (1 - pm)
        # For YES side: our win prob = p_true, payout = (1 - pm) / pm
        if side.upper() == "NO":
            win_prob = Decimal("1") - p
            # NO contract pays (pm) if we win, costs (1-pm)
            # b = pm / (1 - pm)
            b = pm / (Decimal("1") - pm) if pm < 1 else Decimal("999")
            edge = win_prob - (Decimal("1") - pm)
        else:
            win_prob = p
            b = (Decimal("1") - pm) / pm if pm > 0 else Decimal("999")
            edge = win_prob - pm

        kelly_full = self._kelly_formula(win_prob, b)
        kelly_frac = kelly_full * self.kelly_fraction

        # Cap at max position
        kelly_capped = min(kelly_frac, self.max_position_pct)
        kelly_capped = max(kelly_capped, Decimal("0"))  # no negative sizing

        position_dollars = (kelly_capped * self.bankroll).quantize(
            Decimal("0.01"), rounding=ROUND_DOWN
        )
        position_cents = int(position_dollars * 100)

        should_trade = (
            edge >= MIN_EDGE
            and kelly_full > Decimal("0")
            and position_dollars >= Decimal("1.00")  # min $1 trade
        )

        rationale = self._build_rationale(
            p_true, p_market, float(edge), float(kelly_full),
            float(kelly_capped), float(position_dollars), side, should_trade
        )

        return SizingResult(
            p_true=p_true,
            p_market=p_market,
            edge=float(edge),
            kelly_full=float(kelly_full),
            kelly_fractional=float(kelly_capped),
            position_dollars=float(position_dollars),
            position_cents=position_cents,
            bet_on=side.upper(),
            rationale=rationale,
            should_trade=should_trade,
        )

    # ------------------------------------------------------------------
    # NO-side screening (primary strategy per research spec)
    # ------------------------------------------------------------------

    def screen_no_side(
        self, p_true: float, p_market: float, hype_threshold: float = 0.05
    ) -> SizingResult:
        """
        Screen for the NO-side structural edge.

        Per research: target YES contracts where p_market > p_true + 0.05
        (the retail hype premium). 74% win rate documented in Round of 64.
        """
        divergence = p_market - p_true
        if divergence > hype_threshold:
            return self.size(p_true, p_market, side="NO")
        # No edge detected
        return SizingResult(
            p_true=p_true,
            p_market=p_market,
            edge=divergence,
            kelly_full=0.0,
            kelly_fractional=0.0,
            position_dollars=0.0,
            position_cents=0,
            bet_on="NO",
            rationale=f"Insufficient divergence: market={p_market:.3f}, model={p_true:.3f}, gap={divergence:.4f} < threshold={hype_threshold}",
            should_trade=False,
        )

    # ------------------------------------------------------------------
    # Update bankroll (called after fills)
    # ------------------------------------------------------------------

    def update_bankroll(self, new_bankroll: float) -> None:
        self.bankroll = Decimal(str(new_bankroll))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _kelly_formula(p: Decimal, b: Decimal) -> Decimal:
        """
        K* = ( p*(b+1) - 1 ) / b
        Returns 0 if result is negative (no edge).
        """
        if b <= 0:
            return Decimal("0")
        k = (p * (b + Decimal("1")) - Decimal("1")) / b
        return max(k, Decimal("0"))

    @staticmethod
    def _build_rationale(
        p_true, p_market, edge, kelly_full, kelly_capped, dollars, side, should_trade
    ) -> str:
        action = "TRADE" if should_trade else "SKIP"
        return (
            f"[{action}] side={side} | P_true={p_true:.4f} P_market={p_market:.4f} "
            f"edge={edge:.4f} | K_full={kelly_full:.4f} K_frac={kelly_capped:.4f} "
            f"→ ${dollars:.2f}"
        )
