"""
Combo signal engine — combines pattern detection + news sentiment.

Logic:
  Both agree   → strong signal (multiply strengths)
  Only pattern → medium signal (pattern alone)
  Contradict   → skip (don't fight both forces)
  Only news    → handled by existing analyzer.py
"""

import asyncio
from dataclasses import dataclass
from typing import Optional

from patterns.detector import PatternSignal, best_signal, get_rsi, get_trend, scan_all, format_signal
from trading.bybit import get_candles, get_price

SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
TIMEFRAMES = ["15m", "1h", "4h"]


@dataclass
class ComboSignal:
    symbol: str
    timeframe: str
    direction: str          # "long" | "short"
    confidence: float       # 0.0–1.0
    pattern: PatternSignal
    news_aligned: bool
    news_sentiment: str     # "bullish" | "bearish" | "neutral"
    price: float
    rsi: float
    trend: str
    stop_loss_pct: float
    take_profit_pct: float

    def summary(self) -> str:
        arrow = "▲ LONG" if self.direction == "long" else "▼ SHORT"
        alignment = "✓ новости согласны" if self.news_aligned else "~ новости нейтральны"
        return (
            f"{arrow} {self.symbol} @ ${self.price:,.2f} | {self.timeframe}\n"
            f"  Паттерн: {self.pattern.pattern_name} | Уверенность: {self.confidence:.0%}\n"
            f"  RSI: {self.rsi} | Тренд: {self.trend} | {alignment}\n"
            f"  {self.pattern.description}\n"
            f"  SL: -{self.stop_loss_pct}% / TP: +{self.take_profit_pct}%"
        )


def _news_to_sentiment(articles: list, symbol: str) -> str:
    """Quick keyword-based sentiment check on news for this symbol."""
    coin = symbol.split("/")[0].lower()
    name_map = {"btc": ["bitcoin", "btc"], "eth": ["ethereum", "eth"], "sol": ["solana", "sol"]}
    keywords = name_map.get(coin, [coin])

    positive = ["surge", "rally", "bullish", "adoption", "bought", "ETF", "approval",
                 "record", "high", "pump", "moon", "рост", "растёт", "купил", "одобрение"]
    negative = ["crash", "drop", "bearish", "ban", "hack", "sell", "fear", "FUD",
                 "падение", "запрет", "взлом", "страх", "продажи"]

    if not articles:
        return "neutral"
    pos_score = neg_score = 0
    for art in articles[:30]:
        if not hasattr(art, "title") or not hasattr(art, "summary"):
            continue
        text = (art.title + " " + art.summary).lower()
        if any(k in text for k in keywords):
            pos_score += sum(1 for w in positive if w.lower() in text)
            neg_score += sum(1 for w in negative if w.lower() in text)

    if pos_score > neg_score + 2:
        return "bullish"
    if neg_score > pos_score + 2:
        return "bearish"
    return "neutral"


def _combine_confidence(pattern: PatternSignal, news_aligned: bool) -> float:
    base = pattern.strength
    if news_aligned:
        # Both agree — boost confidence significantly
        return min(base * 1.25, 0.95)
    else:
        # Pattern alone — slight reduction
        return base * 0.90


async def scan_crypto_signals(articles: list) -> list[ComboSignal]:
    """
    Scan all symbols across all timeframes.
    Returns actionable combo signals sorted by confidence.
    """
    results = []

    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            try:
                df = get_candles(symbol, tf, limit=100)
                if df is None or len(df) < 20:
                    continue

                sig = best_signal(df)
                if sig is None or sig.direction == "wait":
                    continue

                rsi   = get_rsi(df)
                trend = get_trend(df)
                price = get_price(symbol)

                # RSI filter: don't go long if overbought, don't short if oversold
                if sig.direction == "long"  and rsi > 75:
                    continue
                if sig.direction == "short" and rsi < 25:
                    continue

                # Trend alignment: prefer trading with the trend
                trend_aligned = (
                    (sig.direction == "long"  and trend in ("up", "strong_up")) or
                    (sig.direction == "short" and trend in ("down", "strong_down"))
                )
                if not trend_aligned and sig.strength < 0.80:
                    continue  # skip counter-trend signals unless very strong

                news_sentiment = _news_to_sentiment(articles, symbol)
                news_aligned   = (
                    (sig.direction == "long"  and news_sentiment == "bullish") or
                    (sig.direction == "short" and news_sentiment == "bearish") or
                    news_sentiment == "neutral"  # neutral = don't penalize
                )

                # Skip if news actively contradicts pattern
                news_contradicts = (
                    (sig.direction == "long"  and news_sentiment == "bearish") or
                    (sig.direction == "short" and news_sentiment == "bullish")
                )
                if news_contradicts:
                    continue

                confidence = _combine_confidence(sig, news_aligned and news_sentiment != "neutral")

                results.append(ComboSignal(
                    symbol=symbol,
                    timeframe=tf,
                    direction=sig.direction,
                    confidence=confidence,
                    pattern=sig,
                    news_aligned=news_aligned,
                    news_sentiment=news_sentiment,
                    price=price,
                    rsi=rsi,
                    trend=trend,
                    stop_loss_pct=sig.stop_loss_pct,
                    take_profit_pct=sig.take_profit_pct,
                ))

            except Exception:
                continue

    # Sort: strongest first, deduplicate same symbol (keep best per symbol)
    seen = {}
    for s in sorted(results, key=lambda x: x.confidence, reverse=True):
        if s.symbol not in seen:
            seen[s.symbol] = s
    return list(seen.values())
