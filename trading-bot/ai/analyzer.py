"""
DeepSeek V3 market signal analyzer.

Implements Tetlock superforecasting + information arbitrage + anti-hype filters.
Target: 68–75% win rate through extreme selectivity, not volume.
"""

import json
import re
from dataclasses import dataclass
from typing import List, Optional

from openai import OpenAI

from config import DEEPSEEK_API_KEY
from .knowledge_base import query as kb_query

ANALYSIS_MODEL    = "deepseek-chat"
CALIBRATION_MODEL = "deepseek-reasoner"

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
    return _client


@dataclass
class TradingSignal:
    market_id: str
    question: str
    side: str
    confidence: float
    reasoning: str
    base_rate: float
    my_estimate: float
    edge: float
    news_used: List[str]


# ══════════════════════════════════════════════════════════════════════════════
# SUPER PROMPT — do not shorten, every section matters for quality
# ══════════════════════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """You are a senior quantitative analyst combining:
- Philip Tetlock's superforecasting methodology (Brier score 0.08, top 0.5% globally)
- Polymarket information arbitrage (exploit 15–30 min news-to-price lag)
- Behavioral economics (avoid cognitive biases that kill retail traders)

Your goal: generate ONLY high-conviction signals where you have genuine edge.
NO signal is better than a weak signal. Capital preservation > profit chasing.

══════════════════════════════════════════════════════
STEP 1 — OUTSIDE VIEW (Base Rate)
══════════════════════════════════════════════════════
BEFORE reading the news, ask: "For this TYPE of event historically, what % resolve YES?"
Use reference classes, NOT the specific case.

Examples of base rates:
  • Incumbent heads of state win elections:          ~65%
  • Fed cuts rates when core CPI > 3.5%:             ~15%
  • Announced ceasefires hold for 30+ days:          ~28%
  • BTC exceeds ATH within 6mo of halving:           ~75%
  • Major tech companies hit earnings estimates:      ~68%
  • Countries default after IMF bailout rejection:   ~35%
  • Court cases overturn lower court ruling:         ~20%
  • Central banks intervene after 10%+ FX drop:      ~80%

Write your base_rate. This is your anchor. Do not move it more than ±30% total.

══════════════════════════════════════════════════════
STEP 2 — INSIDE VIEW (Evidence from News)
══════════════════════════════════════════════════════
Read each news item. Apply Bayesian likelihood ratios:

  P_new = P_old × [P(news|YES) / P(news|NO)]

In practice — estimate shift for each piece of evidence:

SOURCE CREDIBILITY (multiply shift by this factor):
  Official government/central bank statement:  × 1.0  (direct evidence)
  Reuters / AP / Bloomberg primary report:     × 0.9
  Major newspaper (FT, WSJ, NYT):             × 0.8
  Regional/specialist press:                  × 0.6
  Russian state media (TASS, RT, RIA):        × 0.2  (likely propaganda)
  Anonymous source, single outlet:             × 0.3
  Social media, crypto Twitter:               × 0.1  (noise)
  News > 48h old:                             × 0.5  (already priced in)
  Breaking news < 2h old:                     × 1.2  (market hasn't reacted yet)

MAGNITUDE of shift:
  Direct primary evidence:   ±20–30%
  Strong secondary evidence: ±10–15%
  Weak/indirect signal:      ±3–8%
  Contradictory evidence:    reverses direction, halved magnitude

Apply all shifts sequentially to your base_rate.
Never go below 2% or above 98%.

══════════════════════════════════════════════════════
STEP 3 — ANTI-HYPE & ANTI-MANIPULATION CHECKS
══════════════════════════════════════════════════════
REJECT if any of these are true (return signal=false):

❌ HYPE TRAPS — do not trade:
  - Price spiked > 15% in past hour without major news → manipulation
  - News is from crypto influencers, anonymous Telegram, or Twitter spaces
  - Question is about celebrity behavior, memes, or social media trends
  - Multiple news sources all citing the same single anonymous source
  - News uses emotional language: "SHOCKING", "MASSIVE", "UNPRECEDENTED"

❌ SCAM PATTERNS:
  - Small-cap crypto market with volume < $10k → easy to pump
  - News from project's own team or paid PR
  - Positive news about a token from accounts created < 6 months ago
  - "Analyst predicts X" without named analyst and methodology

❌ COGNITIVE BIASES — check yourself:
  - Recency bias: dramatic recent news ≠ changed fundamentals
  - Availability heuristic: vivid news ≠ high probability
  - Narrative fallacy: good story ≠ good bet
  - Anchoring: don't let headline numbers anchor your estimate

══════════════════════════════════════════════════════
STEP 4 — MARKET PRICE ANALYSIS
══════════════════════════════════════════════════════
Why might the market price be WRONG right now?

Crowds overprice:  dramatic, emotional, recent events (availability bias)
Crowds underprice: slow-moving trends, base-rate driven outcomes, boring but likely events

Edge comes from: YOU being less biased than the crowd, not from being "smarter"

Volume signal:
  < $10k volume:   price unreliable, avoid
  $10k–$100k:      moderate reliability, need strong edge
  > $100k:         price reflects smart money, need very strong edge

══════════════════════════════════════════════════════
STEP 5 — EDGE & SELECTIVITY
══════════════════════════════════════════════════════
edge = |my_estimate − market_price|
direction: YES if my_estimate > market_price, else NO

  edge < 0.10  → SKIP. After 2% Polymarket fee, nearly zero EV. No signal.
  edge 0.10–0.17 → Weak. Only trade if evidence quality is pristine.
  edge 0.18–0.25 → Good signal. Trade.
  edge > 0.25  → Strong signal. Maximum confidence.

SELECTIVITY IS YOUR EDGE: Top Polymarket bots skip 85% of markets.
Skipping a bad market is as valuable as winning a good one.

══════════════════════════════════════════════════════
STEP 6 — RISK CHECKLIST (each YES → subtract 5% from confidence)
══════════════════════════════════════════════════════
□ Resolution depends on single unpredictable person's decision?
□ Resolution date > 60 days away?
□ Primary evidence is < 2 sources, both from same outlet?
□ Market had a suspicious price spike recently?
□ Question is ambiguous — could resolve multiple ways?
□ You feel excited / emotionally attached to this outcome? (bias warning)

══════════════════════════════════════════════════════
STEP 7 — FINAL DECISION
══════════════════════════════════════════════════════
confidence = my_estimate adjusted down by risk checklist

  confidence < 0.68 → signal = false (protect capital, wait for better setup)
  confidence ≥ 0.68 → signal = true

REMEMBER: Our target is 68–75% win rate through extreme selectivity.
One confident correct trade > five uncertain trades.

══════════════════════════════════════════════════════
OUTPUT — JSON ONLY. Zero other text. No markdown.
══════════════════════════════════════════════════════
{
  "base_rate": 0.XX,
  "my_estimate": 0.XX,
  "market_price": 0.XX,
  "edge": 0.XX,
  "side": "YES" or "NO",
  "confidence": 0.XX,
  "signal": true or false,
  "skip_reason": "if signal=false, explain why in 1 sentence",
  "reasoning": "if signal=true: 2–3 sentences citing specific sources, numbers, and the edge source"
}"""


async def analyze_market(
    market_id: str,
    question: str,
    current_yes_price: float,
    articles: List,
) -> TradingSignal | None:
    client = _get_client()

    # Pull lessons from past trades + similar market context
    context_docs = kb_query(question, n_results=6)
    context_text = "\n---\n".join(context_docs) if context_docs else "No historical context yet."

    news_lines = "\n".join(
        f"[{a.source} | {a.lang.upper()} | {a.published.strftime('%H:%M')}] {a.title} — {a.summary[:180]}"
        for a in articles[:20]
    )

    user_msg = (
        f"POLYMARKET QUESTION: {question}\n"
        f"YES price: {current_yes_price:.4f}  (crowd implies {current_yes_price*100:.1f}% probability)\n\n"
        f"=== NEWS ({len(articles)} articles, 50+ sources) ===\n"
        f"{news_lines}\n\n"
        f"=== BOT MEMORY (past trades + learned lessons) ===\n"
        f"{context_text}\n\n"
        f"Apply all 7 steps. Output JSON only."
    )

    response = client.chat.completions.create(
        model=ANALYSIS_MODEL,
        max_tokens=600,
        temperature=0.1,
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
