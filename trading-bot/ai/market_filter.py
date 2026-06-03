"""
Market filter — rejects markets before analysis reaches DeepSeek.
Saves API costs and improves overall win rate by avoiding bad markets.

Based on research: thin markets, hype categories, manipulation signals
are the main cause of AI bot losses on Polymarket.
"""

from dataclasses import dataclass
from typing import Tuple


# Categories with low predictability / high manipulation risk
HYPE_KEYWORDS = [
    "meme", "viral", "celebrity", "kardashian", "elon tweet", "doge",
    "shib", "pepe", "nft", "metaverse", "will trump say", "will biden say",
    "first to", "most followers", "goes viral", "trending",
]

SCAM_SIGNALS = [
    "guaranteed", "100%", "rug", "anonymous team", "no whitepaper",
    "get rich", "moon", "lambo",
]

# Best performing categories (research-backed)
HIGH_EDGE_KEYWORDS = [
    "fed", "federal reserve", "interest rate", "cpi", "inflation", "gdp",
    "election", "vote", "referendum", "parliament", "senate", "congress",
    "bitcoin", "btc", "ethereum", "eth",  # only large-cap crypto
    "ceasefire", "peace talks", "sanctions", "war", "conflict",
    "court", "verdict", "ruling", "supreme court",
    "ipo", "merger", "acquisition", "bankruptcy",
    "world cup", "championship", "olympic",
]


@dataclass
class FilterResult:
    passed: bool
    reason: str
    quality_score: float  # 0.0–1.0, higher = better market to trade


def filter_market(
    question: str,
    volume_usd: float,
    yes_price: float,
    days_to_resolution: int | None = None,
) -> FilterResult:
    q = question.lower()

    # ── Hard rejects ──────────────────────────────────────────────────────────

    if volume_usd < 5_000:
        return FilterResult(False, f"Volume too low (${volume_usd:,.0f} < $5k) — easy to manipulate", 0.0)

    if any(kw in q for kw in HYPE_KEYWORDS):
        matched = next(kw for kw in HYPE_KEYWORDS if kw in q)
        return FilterResult(False, f"Hype/entertainment market ('{matched}') — unpredictable", 0.0)

    if any(kw in q for kw in SCAM_SIGNALS):
        matched = next(kw for kw in SCAM_SIGNALS if kw in q)
        return FilterResult(False, f"Scam signal detected ('{matched}')", 0.0)

    # Price extremes — market already decided, no edge
    if yes_price < 0.03 or yes_price > 0.97:
        return FilterResult(False, f"Price already at extreme ({yes_price:.2f}) — no edge left", 0.0)

    if days_to_resolution is not None:
        if days_to_resolution > 180:
            return FilterResult(False, f"Resolution too far ({days_to_resolution}d > 180d) — too uncertain", 0.0)
        if days_to_resolution < 1:
            return FilterResult(False, "Resolves today — too late for news-based edge", 0.0)

    # ── Quality score ─────────────────────────────────────────────────────────

    score = 0.5  # baseline

    # Volume bonus
    if volume_usd > 100_000:
        score += 0.2
    elif volume_usd > 50_000:
        score += 0.1

    # High-edge category bonus
    if any(kw in q for kw in HIGH_EDGE_KEYWORDS):
        score += 0.2

    # Sweet spot: 14–60 days to resolution
    if days_to_resolution and 14 <= days_to_resolution <= 60:
        score += 0.1

    # Price in tradeable range (not already settled)
    if 0.25 <= yes_price <= 0.75:
        score += 0.1

    score = min(score, 1.0)

    return FilterResult(True, "Market passed all filters", round(score, 2))
