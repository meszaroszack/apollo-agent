"""
AlphaEngine — Four-Factors model for computing P_true from BALLDONTLIE data.

Statistical Foundation
----------------------
Win probability is modeled using the "Four Factors" framework (Dean Oliver):

    1. Effective Field Goal %  (eFG)  — shooting efficiency
    2. Turnover Rate           (TO%)  — ball security
    3. Rebounding Rate         (REB)  — offensive / defensive board %
    4. Free Throw Rate         (FTR)  — getting to the line

Critical alpha finding (per research spec):
    +1 rebound/game → +2.62% win probability

Market divergence threshold:
    P_market > P_true + 0.05  →  NO-side trade signal (retail hype premium)
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

log = logging.getLogger("apollo.alpha_engine")

BALLDONTLIE_BASE = "https://api.balldontlie.io/v1"
REBOUND_WIN_PROB_PER_GAME = 0.0262   # +1 reb/game = +2.62% win prob (research finding)
HYPE_THRESHOLD = 0.05                 # P_market - P_true > 5% → NO-side signal


# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class TeamFactors:
    team_id: int
    team_name: str
    efg_pct: float       # Effective FG% = (FGM + 0.5*3PM) / FGA
    to_rate: float       # Turnover rate = TOV / (FGA + 0.44*FTA + TOV)
    reb_rate: float      # Rebounding rate = OREB / (OREB + Opp_DREB)
    ftr: float           # Free throw rate = FTA / FGA
    avg_rebounds: float  # Simple avg rebounds per game (for rebound alpha)
    sample_games: int    # Games used in the calculation


@dataclass
class MatchupSignal:
    team_a_id: int
    team_a_name: str
    team_b_id: int
    team_b_name: str
    p_true_a: float         # Model probability: team A wins
    p_true_b: float         # = 1 - p_true_a
    divergence_a: float     # p_market_a - p_true_a  (positive = market overvalues A)
    divergence_b: float
    signal: str             # "NO_A", "NO_B", "YES_A", "YES_B", or "NEUTRAL"
    edge: float             # Magnitude of the exploitable edge
    rationale: str


# ──────────────────────────────────────────────────────────────────────────────
# BALLDONTLIE Client
# ──────────────────────────────────────────────────────────────────────────────

class BallDontLieClient:
    """
    Async client for BALLDONTLIE NCAAB API.
    Implements cursor-based pagination for complete data ingestion.
    """

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=BALLDONTLIE_BASE,
            headers={"Authorization": api_key},
            timeout=30,
        )

    async def close(self):
        await self._client.aclose()

    async def _paginate(self, path: str, params: dict) -> list[dict]:
        """Recursively fetch all pages using cursor-based pagination."""
        results = []
        cursor = None

        while True:
            p = {**params, "per_page": 100}
            if cursor:
                p["cursor"] = cursor

            resp = await self._client.get(path, params=p)
            resp.raise_for_status()
            data = resp.json()

            results.extend(data.get("data", []))

            meta = data.get("meta", {})
            next_cursor = meta.get("next_cursor")
            if not next_cursor:
                break
            cursor = next_cursor

        return results

    async def get_team_stats(
        self,
        team_id: int,
        seasons: list[int] = None,
        postseason_only: bool = True,
    ) -> list[dict]:
        """
        Fetch box-score stats for a team.  Default to tournament (postseason) games.
        """
        params = {
            "team_ids[]": team_id,
            "postseason": str(postseason_only).lower(),
        }
        if seasons:
            params["seasons[]"] = seasons

        games = await self._paginate("/stats", params)
        return games

    async def get_team_season_averages(
        self, team_id: int, season: int
    ) -> Optional[dict]:
        """Fetch season-average box score for a team."""
        resp = await self._client.get(
            "/season_averages",
            params={"team_ids[]": team_id, "season": season, "type": "regularSeason"},
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return data[0] if data else None

    async def get_tournament_bracket(self, season: int) -> list[dict]:
        """Fetch bracket / tournament structure for a season."""
        resp = await self._client.get("/tournament_rounds", params={"season": season})
        resp.raise_for_status()
        return resp.json().get("data", [])

    async def search_team(self, name: str) -> Optional[dict]:
        """Search for a team by name."""
        resp = await self._client.get("/teams", params={"search": name, "per_page": 5})
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return data[0] if data else None


# ──────────────────────────────────────────────────────────────────────────────
# Four Factors Calculator
# ──────────────────────────────────────────────────────────────────────────────

class FourFactorsCalculator:
    """
    Computes the Four Factors from raw box-score stat rows.
    """

    @staticmethod
    def from_season_average(team_id: int, team_name: str, avg: dict) -> TeamFactors:
        """
        Build TeamFactors from a BALLDONTLIE season_averages record.
        """
        fgm = float(avg.get("fgm", 0) or 0)
        fga = float(avg.get("fga", 1) or 1)
        fg3m = float(avg.get("fg3m", 0) or 0)
        ftm = float(avg.get("ftm", 0) or 0)
        fta = float(avg.get("fta", 1) or 1)
        tov = float(avg.get("turnover", 0) or 0)
        oreb = float(avg.get("oreb", 0) or 0)
        dreb = float(avg.get("dreb", 0) or 0)
        reb = float(avg.get("reb", 0) or 0)
        games = int(avg.get("games_played", 1) or 1)

        # Four Factors
        efg = (fgm + 0.5 * fg3m) / fga if fga > 0 else 0
        to_rate = tov / (fga + 0.44 * fta + tov) if (fga + 0.44 * fta + tov) > 0 else 0
        reb_rate = oreb / (oreb + 1) if (oreb + 1) > 0 else 0  # simplified without opp data
        ftr = fta / fga if fga > 0 else 0

        return TeamFactors(
            team_id=team_id,
            team_name=team_name,
            efg_pct=efg,
            to_rate=to_rate,
            reb_rate=reb_rate,
            ftr=ftr,
            avg_rebounds=reb,
            sample_games=games,
        )

    @staticmethod
    def four_factors_score(f: TeamFactors) -> float:
        """
        Compute a composite score from the Four Factors.
        Weights from Dean Oliver's research:
            eFG%  → 0.40
            TO%   → 0.25 (lower is better — inverted)
            REB   → 0.20
            FTR   → 0.15
        """
        return (
            0.40 * f.efg_pct
            - 0.25 * f.to_rate    # penalty for turnovers
            + 0.20 * f.reb_rate
            + 0.15 * f.ftr
        )


# ──────────────────────────────────────────────────────────────────────────────
# Alpha Engine
# ──────────────────────────────────────────────────────────────────────────────

class AlphaEngine:
    """
    Orchestrates the full alpha-generation pipeline:
        1. Fetch team stats from BALLDONTLIE
        2. Compute Four Factors → P_true
        3. Apply rebound alpha adjustment (+2.62% per rebound differential)
        4. Compare against Kalshi P_market
        5. Emit a MatchupSignal

    Parameters
    ----------
    bdl_client : BallDontLieClient
    season : int  Current NCAAB season year (e.g. 2026)
    """

    def __init__(self, bdl_client: BallDontLieClient, season: int = 2026):
        self._bdl = bdl_client
        self._season = season
        self._calc = FourFactorsCalculator()

    async def analyze_matchup(
        self,
        team_a_id: int,
        team_a_name: str,
        team_b_id: int,
        team_b_name: str,
        p_market_a: float,   # Kalshi YES price for team A winning
    ) -> MatchupSignal:
        """
        Full pipeline: fetch stats → compute P_true → generate signal.
        """
        # Fetch season averages in parallel
        avg_a, avg_b = await asyncio.gather(
            self._bdl.get_team_season_averages(team_a_id, self._season),
            self._bdl.get_team_season_averages(team_b_id, self._season),
        )

        if not avg_a or not avg_b:
            log.warning("Missing season averages for %s or %s", team_a_name, team_b_name)
            return self._neutral_signal(team_a_id, team_a_name, team_b_id, team_b_name, p_market_a)

        factors_a = FourFactorsCalculator.from_season_average(team_a_id, team_a_name, avg_a)
        factors_b = FourFactorsCalculator.from_season_average(team_b_id, team_b_name, avg_b)

        p_true_a = self._compute_p_true(factors_a, factors_b)
        p_true_b = 1.0 - p_true_a

        # Apply rebound alpha: +1 reb/game = +2.62% win probability
        reb_diff = factors_a.avg_rebounds - factors_b.avg_rebounds
        rebound_adjustment = reb_diff * REBOUND_WIN_PROB_PER_GAME
        p_true_a_adjusted = max(0.01, min(0.99, p_true_a + rebound_adjustment))
        p_true_b_adjusted = 1.0 - p_true_a_adjusted

        p_market_b = 1.0 - p_market_a

        divergence_a = p_market_a - p_true_a_adjusted
        divergence_b = p_market_b - p_true_b_adjusted

        signal, edge = self._classify_signal(divergence_a, divergence_b)

        rationale = (
            f"{team_a_name} FF-score={FourFactorsCalculator.four_factors_score(factors_a):.4f} "
            f"P_true={p_true_a_adjusted:.4f} P_market={p_market_a:.4f} div={divergence_a:+.4f} | "
            f"{team_b_name} FF-score={FourFactorsCalculator.four_factors_score(factors_b):.4f} "
            f"P_true={p_true_b_adjusted:.4f} P_market={p_market_b:.4f} div={divergence_b:+.4f} | "
            f"reb_diff={reb_diff:+.2f} adj={rebound_adjustment:+.4f} | signal={signal}"
        )

        return MatchupSignal(
            team_a_id=team_a_id,
            team_a_name=team_a_name,
            team_b_id=team_b_id,
            team_b_name=team_b_name,
            p_true_a=p_true_a_adjusted,
            p_true_b=p_true_b_adjusted,
            divergence_a=divergence_a,
            divergence_b=divergence_b,
            signal=signal,
            edge=edge,
            rationale=rationale,
        )

    # ------------------------------------------------------------------
    # P_true computation
    # ------------------------------------------------------------------

    def _compute_p_true(self, a: TeamFactors, b: TeamFactors) -> float:
        """
        Convert Four Factors composite scores into a head-to-head win probability
        using a log5-style formula.
        """
        score_a = FourFactorsCalculator.four_factors_score(a)
        score_b = FourFactorsCalculator.four_factors_score(b)

        # Normalize to [0.05, 0.95] to avoid extreme predictions
        total = score_a + score_b
        if total <= 0:
            return 0.5

        raw_p = score_a / total
        return max(0.05, min(0.95, raw_p))

    # ------------------------------------------------------------------
    # Signal classification
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_signal(div_a: float, div_b: float) -> tuple[str, float]:
        """
        Classify the tradeable signal based on market divergence.
        Per spec: target NO-side where P_market > P_true + 0.05
        """
        if div_a > HYPE_THRESHOLD:
            return "NO_A", div_a
        if div_b > HYPE_THRESHOLD:
            return "NO_B", div_b
        if div_a < -HYPE_THRESHOLD:
            return "YES_A", abs(div_a)
        if div_b < -HYPE_THRESHOLD:
            return "YES_B", abs(div_b)
        return "NEUTRAL", 0.0

    @staticmethod
    def _neutral_signal(ta_id, ta_name, tb_id, tb_name, p_market_a) -> MatchupSignal:
        return MatchupSignal(
            team_a_id=ta_id, team_a_name=ta_name,
            team_b_id=tb_id, team_b_name=tb_name,
            p_true_a=0.5, p_true_b=0.5,
            divergence_a=p_market_a - 0.5,
            divergence_b=(1 - p_market_a) - 0.5,
            signal="NEUTRAL", edge=0.0,
            rationale="Insufficient data — defaulting to NEUTRAL",
        )
