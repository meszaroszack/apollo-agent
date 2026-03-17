"""
SentimentGuardrail — Perplexity Sonar API integration (toggleable).

Logic
-----
Before executing a trade, query Perplexity for real-time news on the matchup.
Extract a sentiment score in [-1.0, 1.0].
If score < SENTIMENT_ABORT_THRESHOLD (-0.4), abort the trade.

The guardrail is OPTIONAL — if no Perplexity API key is configured, it is skipped.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

import httpx

log = logging.getLogger("apollo.sentiment")

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
SENTIMENT_ABORT_THRESHOLD = -0.4
SENTIMENT_MODEL = "sonar"   # Perplexity's real-time search model


@dataclass
class SentimentResult:
    team_a: str
    team_b: str
    score: float           # -1.0 (very negative) to +1.0 (very positive)
    summary: str           # Human-readable news summary
    sources: list[str]
    should_abort: bool
    reason: str


class SentimentGuardrail:
    """
    Optional Perplexity Sonar sentiment layer.

    Parameters
    ----------
    api_key : str | None
        Perplexity API key.  If None, the guardrail is disabled.
    abort_threshold : float
        Score below which the trade is aborted (default -0.4).
    """

    def __init__(
        self,
        api_key: Optional[str],
        abort_threshold: float = SENTIMENT_ABORT_THRESHOLD,
    ):
        self._api_key = api_key
        self._abort_threshold = abort_threshold
        self.enabled = api_key is not None and len(api_key.strip()) > 0

    @property
    def is_enabled(self) -> bool:
        return self.enabled

    async def evaluate(
        self, team_a: str, team_b: str, primary_team: str
    ) -> SentimentResult:
        """
        Evaluate current sentiment for a matchup.

        Parameters
        ----------
        team_a : str
            Home / favored team name.
        team_b : str
            Away / underdog team name.
        primary_team : str
            The team we are trading on (used to focus sentiment).
        """
        if not self.enabled:
            return SentimentResult(
                team_a=team_a, team_b=team_b, score=0.0,
                summary="Sentiment guardrail disabled (no API key)",
                sources=[], should_abort=False,
                reason="Guardrail not configured",
            )

        queries = self._build_queries(team_a, team_b, primary_team)
        raw_response, sources = await self._query_perplexity(queries)
        score = self._extract_score(raw_response)

        should_abort = score < self._abort_threshold
        reason = (
            f"Negative momentum detected (score={score:.2f} < threshold={self._abort_threshold})"
            if should_abort
            else f"Sentiment OK (score={score:.2f})"
        )

        if should_abort:
            log.warning(
                "SENTIMENT ABORT: %s vs %s — score=%.2f < %.2f",
                team_a, team_b, score, self._abort_threshold,
            )

        return SentimentResult(
            team_a=team_a, team_b=team_b, score=score,
            summary=raw_response[:500],
            sources=sources,
            should_abort=should_abort,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Query construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_queries(team_a: str, team_b: str, primary_team: str) -> str:
        return (
            f"Latest injury reports and player availability for {team_a} vs {team_b} NCAA tournament 2026. "
            f"Any breaking news, locker room issues, or momentum shifts for {primary_team}. "
            f"Provide a sentiment score from -1 (very negative) to +1 (very positive) "
            f"for {primary_team}'s tournament chances. Format: SENTIMENT_SCORE: <number>"
        )

    # ------------------------------------------------------------------
    # Perplexity API call
    # ------------------------------------------------------------------

    async def _query_perplexity(self, prompt: str) -> tuple[str, list[str]]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": SENTIMENT_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a sports analytics assistant specializing in NCAA basketball. "
                        "Analyze the latest news and provide actionable sentiment assessments. "
                        "Always end with 'SENTIMENT_SCORE: <value>' where value is between -1.0 and 1.0."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "return_citations": True,
            "search_recency_filter": "day",  # Only last 24 hours for recency
        }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(PERPLEXITY_API_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        sources = [c.get("url", "") for c in data.get("citations", [])]
        return content, sources

    # ------------------------------------------------------------------
    # Score extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_score(text: str) -> float:
        """
        Parse the SENTIMENT_SCORE: <value> tag from the response.
        Falls back to keyword-based heuristic if tag is missing.
        """
        # Primary: explicit tag
        match = re.search(r"SENTIMENT_SCORE:\s*([-+]?\d*\.?\d+)", text, re.IGNORECASE)
        if match:
            score = float(match.group(1))
            return max(-1.0, min(1.0, score))

        # Fallback: keyword heuristics
        text_lower = text.lower()
        negative_keywords = ["injured", "out", "suspended", "illness", "questionable",
                             "doubtful", "lost", "slump", "controversy", "benched"]
        positive_keywords = ["healthy", "momentum", "hot streak", "undefeated",
                             "dominant", "sharp", "confidence", "ready"]

        neg_count = sum(1 for kw in negative_keywords if kw in text_lower)
        pos_count = sum(1 for kw in positive_keywords if kw in text_lower)

        if neg_count > pos_count:
            score = -0.2 * neg_count
        elif pos_count > neg_count:
            score = 0.2 * pos_count
        else:
            score = 0.0

        return max(-1.0, min(1.0, score))
