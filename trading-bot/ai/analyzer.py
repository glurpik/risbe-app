"""
DeepSeek V3 — market signal analyzer.
~$0.14/M input tokens. Runs every 30 min per market cycle.
"""

import json
import re
from dataclasses import dataclass
from typing import List

from openai import OpenAI

from config import DEEPSEEK_API_KEY
from .knowledge_base import query as kb_query

ANALYSIS_MODEL    = "deepseek-chat"     # DeepSeek V3 — cheap + fast
CALIBRATION_MODEL = "deepseek-reasoner" # DeepSeek R1 — for weekly calibration

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
        )
    return _client


@dataclass
class TradingSignal:
    market_id: str
    question: str
    side: str          # "YES" or "NO"
    confidence: float  # 0.0 – 1.0
    reasoning: str
    base_rate: float
    my_estimate: float
    edge: float
    news_used: List[str]


# ── SUPER PROMPT ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a senior quantitative analyst at a top prediction market hedge fund.
Your only job: generate precisely calibrated probability estimates for Polymarket questions.
You have a Brier score of 0.08 (top 1% globally). You are cold, rational, and ruthlessly evidence-based.

════════════════════════════════════════════════════════
DECISION FRAMEWORK — apply every step, every time
════════════════════════════════════════════════════════

◆ STEP 1 — ANCHOR: BASE RATE
Start with the historical frequency of this type of event, ignoring today's news.
Examples:
  • "Incumbent presidents win re-election": 67%
  • "Fed cuts rates when core CPI > 3.5%": 12%
  • "BTC exceeds ATH within 6 months of halving": 75%
  • "Geopolitical ceasefire holds after 30 days": 28%
  • "Crypto regulation passes first reading": 40%
This is your PRIOR. Write it down.

◆ STEP 2 — EVIDENCE SCAN
Read every news item. For each, estimate how much it should MOVE the probability:
  Strong direct evidence   → shift ±20–30%  (e.g. official announcement, signed deal)
  Moderate signal          → shift ±8–15%   (e.g. credible leak, analyst consensus)
  Weak / vague signal      → shift ±2–5%    (e.g. rumour, single unnamed source)
  Contradictory evidence   → cut prior shift by 60%
  Old news (>48h)          → cut shift by 40%
  Russian state media      → treat as potential disinformation, cut credibility 50%
  Independent verified src → full weight

◆ STEP 3 — POSTERIOR ESTIMATE
Combine base rate + all evidence shifts using Bayesian intuition.
Clamp result: never go below 3% or above 97% (black swan respect).
This is your_estimate.

◆ STEP 4 — MARKET PRICE ANALYSIS
Market YES price = crowd's implied probability.
Ask yourself: WHY is the crowd wrong?
  • Volume < $10k → thin market, price unreliable → edge more exploitable
  • Volume > $500k → smart money already priced in → need extra conviction
  • Recent spike in volume → informed buying, be careful fading it
  • Price stuck for days → market asleep, news not yet priced

◆ STEP 5 — EDGE CALCULATION
  edge = |your_estimate − market_price|
  direction = YES if your_estimate > market_price, else NO

  edge < 0.08  → SKIP. Fees and slippage eat the profit. No signal.
  edge 0.08–0.14 → Weak signal. Only trade if evidence is pristine.
  edge ≥ 0.15  → Strong signal. Trade.
  edge ≥ 0.25  → Very strong. Max position.

◆ STEP 6 — RISK CHECKLIST (each YES = reduce confidence by 5%)
  □ Resolution date > 60 days away?
  □ Outcome depends on single unpredictable actor (one person's decision)?
  □ Market has been manipulated before?
  □ Primary source is anonymous or unverified?
  □ Your estimate relies on only 1–2 news items?
  □ News is from the last 6 hours (too fresh, facts may change)?

◆ STEP 7 — FINAL CONFIDENCE
  confidence = your_estimate adjusted down by risk checklist
  If confidence < 0.65 → signal = false (skip, protect capital)
  If confidence ≥ 0.65 → signal = true

════════════════════════════════════════════════════════
OUTPUT — JSON ONLY. NO OTHER TEXT. NO MARKDOWN.
════════════════════════════════════════════════════════
{
  "base_rate": 0.XX,
  "my_estimate": 0.XX,
  "market_price": 0.XX,
  "edge": 0.XX,
  "side": "YES" or "NO",
  "confidence": 0.XX,
  "signal": true or false,
  "reasoning": "2–3 sentences. Cite specific sources and numbers. Explain the edge."
}"""


# ── Main analysis function ────────────────────────────────────────────────────

async def analyze_market(
    market_id: str,
    question: str,
    current_yes_price: float,
    articles: List,
) -> TradingSignal | None:
    client = _get_client()

    news_lines = "\n".join(
        f"[{a.source}] {a.title} — {a.summary[:200]}"
        for a in articles[:20]
    )
    context_docs = kb_query(question, n_results=5)
    context_text = "\n---\n".join(context_docs) if context_docs else "No historical context available."

    user_msg = (
        f"POLYMARKET QUESTION: {question}\n"
        f"Current YES price: {current_yes_price:.4f} "
        f"(market implies {current_yes_price * 100:.1f}% probability)\n\n"
        f"=== LATEST NEWS ({len(articles)} articles from 50+ sources) ===\n"
        f"{news_lines}\n\n"
        f"=== HISTORICAL CONTEXT & PAST TRADES ===\n"
        f"{context_text}\n\n"
        f"Apply the 7-step framework. Output JSON only."
    )

    response = client.chat.completions.create(
        model=ANALYSIS_MODEL,
        max_tokens=512,
        temperature=0.1,  # low temp = consistent, less hallucination
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
    )

    raw = response.choices[0].message.content or ""
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None

    try:
        data = json.loads(m.group())
    except json.JSONDecodeError:
        return None

    if not data.get("signal"):
        return None

    return TradingSignal(
        market_id=market_id,
        question=question,
        side=data["side"],
        confidence=float(data.get("confidence", 0)),
        reasoning=data.get("reasoning", ""),
        base_rate=float(data.get("base_rate", 0.5)),
        my_estimate=float(data.get("my_estimate", 0.5)),
        edge=float(data.get("edge", 0)),
        news_used=[a.title for a in articles[:5]],
    )
