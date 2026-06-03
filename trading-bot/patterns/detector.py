"""
Pattern detector — candlestick + chart patterns, multi-timeframe.

Паттерн сам определяет таймфрейм:
  Свечной (молот, поглощение)  → 15m / 1h
  Графический (H&S, клин)      → 1h / 4h

Returns PatternSignal with direction, strength, and recommended timeframe.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class PatternSignal:
    pattern_name: str
    direction: str        # "long" | "short" | "wait"
    strength: float       # 0.0 – 1.0
    timeframe: str        # "15m" | "1h" | "4h"
    description: str
    stop_loss_pct: float  # suggested stop loss %
    take_profit_pct: float


# ══════════════════════════════════════════════════════════════════════════════
# CANDLESTICK PATTERNS
# ══════════════════════════════════════════════════════════════════════════════

def _body(df: pd.DataFrame, i: int) -> float:
    return abs(df["close"].iloc[i] - df["open"].iloc[i])

def _range(df: pd.DataFrame, i: int) -> float:
    return df["high"].iloc[i] - df["low"].iloc[i]

def _is_bullish(df: pd.DataFrame, i: int) -> bool:
    return df["close"].iloc[i] > df["open"].iloc[i]

def _is_bearish(df: pd.DataFrame, i: int) -> bool:
    return df["close"].iloc[i] < df["open"].iloc[i]


def detect_hammer(df: pd.DataFrame) -> Optional[PatternSignal]:
    """Молот — разворот вверх после нисходящего тренда."""
    i = -1
    c = df["close"].iloc[i]
    o = df["open"].iloc[i]
    h = df["high"].iloc[i]
    l = df["low"].iloc[i]
    body = abs(c - o)
    lower_wick = min(c, o) - l
    upper_wick = h - max(c, o)
    total = h - l
    if total == 0:
        return None

    if lower_wick >= 2 * body and upper_wick <= 0.1 * total and body > 0:
        # Check downtrend before
        prev_closes = df["close"].iloc[-6:-1]
        if prev_closes.is_monotonic_decreasing or prev_closes.iloc[-1] < prev_closes.iloc[0]:
            return PatternSignal(
                pattern_name="Молот",
                direction="long",
                strength=0.72,
                timeframe="1h",
                description="Длинная нижняя тень = отвержение цен ниже. Возможный разворот вверх.",
                stop_loss_pct=1.5,
                take_profit_pct=3.0,
            )
    return None


def detect_inverted_hammer(df: pd.DataFrame) -> Optional[PatternSignal]:
    """Перевёрнутый молот."""
    i = -1
    c = df["close"].iloc[i]
    o = df["open"].iloc[i]
    h = df["high"].iloc[i]
    l = df["low"].iloc[i]
    body = abs(c - o)
    upper_wick = h - max(c, o)
    lower_wick = min(c, o) - l
    total = h - l
    if total == 0 or body == 0:
        return None
    if upper_wick >= 2 * body and lower_wick <= 0.1 * total:
        return PatternSignal(
            pattern_name="Перевёрнутый молот",
            direction="long",
            strength=0.60,
            timeframe="1h",
            description="Длинная верхняя тень = попытка роста. Слабее молота, нужно подтверждение.",
            stop_loss_pct=1.8,
            take_profit_pct=2.5,
        )
    return None


def detect_engulfing(df: pd.DataFrame) -> Optional[PatternSignal]:
    """Поглощение — один из сильнейших разворотных паттернов."""
    if len(df) < 2:
        return None
    prev_o, prev_c = df["open"].iloc[-2], df["close"].iloc[-2]
    curr_o, curr_c = df["open"].iloc[-1], df["close"].iloc[-1]

    # Бычье поглощение
    if prev_c < prev_o and curr_c > curr_o:
        if curr_o <= prev_c and curr_c >= prev_o:
            return PatternSignal(
                pattern_name="Бычье поглощение",
                direction="long",
                strength=0.82,
                timeframe="1h",
                description="Бычья свеча полностью поглотила медвежью. Сильный разворотный сигнал.",
                stop_loss_pct=1.2,
                take_profit_pct=4.0,
            )

    # Медвежье поглощение
    if prev_c > prev_o and curr_c < curr_o:
        if curr_o >= prev_c and curr_c <= prev_o:
            return PatternSignal(
                pattern_name="Медвежье поглощение",
                direction="short",
                strength=0.82,
                timeframe="1h",
                description="Медвежья свеча полностью поглотила бычью. Сильный сигнал на снижение.",
                stop_loss_pct=1.2,
                take_profit_pct=4.0,
            )
    return None


def detect_doji(df: pd.DataFrame) -> Optional[PatternSignal]:
    """Доджи — нерешительность рынка."""
    i = -1
    body = _body(df, i)
    total = _range(df, i)
    if total == 0:
        return None
    if body / total < 0.08:
        return PatternSignal(
            pattern_name="Доджи",
            direction="wait",
            strength=0.50,
            timeframe="15m",
            description="Тело почти нет — покупатели и продавцы равны. Жди следующей свечи.",
            stop_loss_pct=1.0,
            take_profit_pct=2.0,
        )
    return None


def detect_morning_star(df: pd.DataFrame) -> Optional[PatternSignal]:
    """Утренняя звезда — разворот после нисходящего движения."""
    if len(df) < 3:
        return None
    c1, o1 = df["close"].iloc[-3], df["open"].iloc[-3]  # большая медвежья
    c2, o2 = df["close"].iloc[-2], df["open"].iloc[-2]  # маленькое тело
    c3, o3 = df["close"].iloc[-1], df["open"].iloc[-1]  # большая бычья

    body1 = abs(c1 - o1)
    body2 = abs(c2 - o2)
    body3 = abs(c3 - o3)

    if (c1 < o1 and body2 < body1 * 0.4 and
            c3 > o3 and body3 > body1 * 0.5 and
            max(c2, o2) < min(c1, o1)):
        return PatternSignal(
            pattern_name="Утренняя звезда",
            direction="long",
            strength=0.85,
            timeframe="4h",
            description="Три свечи: падение → пауза → рост. Один из надёжнейших паттернов разворота.",
            stop_loss_pct=1.0,
            take_profit_pct=5.0,
        )
    return None


def detect_shooting_star(df: pd.DataFrame) -> Optional[PatternSignal]:
    """Падающая звезда — разворот вниз."""
    i = -1
    o, c, h, l = df["open"].iloc[i], df["close"].iloc[i], df["high"].iloc[i], df["low"].iloc[i]
    upper_wick = h - max(o, c)
    body = abs(c - o)
    lower_wick = min(o, c) - l
    total = h - l
    if total == 0 or body == 0:
        return None
    if upper_wick >= 2 * body and lower_wick <= 0.1 * total:
        prev_closes = df["close"].iloc[-6:-1]
        if prev_closes.is_monotonic_increasing or prev_closes.iloc[-1] > prev_closes.iloc[0]:
            return PatternSignal(
                pattern_name="Падающая звезда",
                direction="short",
                strength=0.72,
                timeframe="1h",
                description="Длинная верхняя тень = отвержение высоких цен. Разворот вниз.",
                stop_loss_pct=1.5,
                take_profit_pct=3.0,
            )
    return None


# ══════════════════════════════════════════════════════════════════════════════
# CHART PATTERNS (требуют больше свечей)
# ══════════════════════════════════════════════════════════════════════════════

def detect_double_bottom(df: pd.DataFrame) -> Optional[PatternSignal]:
    """Двойное дно — мощный сигнал разворота вверх."""
    if len(df) < 30:
        return None
    lows = df["low"].values
    # Ищем два локальных минимума примерно на одном уровне
    window = 5
    local_mins = []
    for i in range(window, len(lows) - window):
        if lows[i] == min(lows[i-window:i+window+1]):
            local_mins.append((i, lows[i]))

    if len(local_mins) < 2:
        return None

    last_two = local_mins[-2:]
    i1, v1 = last_two[0]
    i2, v2 = last_two[1]

    if abs(v1 - v2) / max(v1, v2) < 0.02 and (i2 - i1) >= 8:
        neckline = df["high"].iloc[i1:i2].max()
        current = df["close"].iloc[-1]
        if current > neckline * 0.98:
            return PatternSignal(
                pattern_name="Двойное дно",
                direction="long",
                strength=0.88,
                timeframe="4h",
                description=f"Два дна на уровне ~{v1:.0f}. Пробой линии шеи {neckline:.0f} = подтверждение.",
                stop_loss_pct=1.5,
                take_profit_pct=6.0,
            )
    return None


def detect_double_top(df: pd.DataFrame) -> Optional[PatternSignal]:
    """Двойная вершина — сигнал разворота вниз."""
    if len(df) < 30:
        return None
    highs = df["high"].values
    window = 5
    local_maxes = []
    for i in range(window, len(highs) - window):
        if highs[i] == max(highs[i-window:i+window+1]):
            local_maxes.append((i, highs[i]))

    if len(local_maxes) < 2:
        return None

    last_two = local_maxes[-2:]
    i1, v1 = last_two[0]
    i2, v2 = last_two[1]

    if abs(v1 - v2) / max(v1, v2) < 0.02 and (i2 - i1) >= 8:
        neckline = df["low"].iloc[i1:i2].min()
        current = df["close"].iloc[-1]
        if current < neckline * 1.02:
            return PatternSignal(
                pattern_name="Двойная вершина",
                direction="short",
                strength=0.85,
                timeframe="4h",
                description=f"Две вершины на уровне ~{v1:.0f}. Пробой поддержки {neckline:.0f} = сигнал шорт.",
                stop_loss_pct=1.5,
                take_profit_pct=6.0,
            )
    return None


def detect_triangle(df: pd.DataFrame) -> Optional[PatternSignal]:
    """Сужающийся треугольник — накопление перед пробоем."""
    if len(df) < 20:
        return None
    recent = df.iloc[-20:]
    highs = recent["high"].values
    lows  = recent["low"].values

    high_slope = np.polyfit(range(len(highs)), highs, 1)[0]
    low_slope  = np.polyfit(range(len(lows)),  lows,  1)[0]

    # Сужение: верхняя линия падает, нижняя растёт
    if high_slope < -0.01 and low_slope > 0.01:
        width_start = highs[0] - lows[0]
        width_end   = highs[-1] - lows[-1]
        compression = 1 - (width_end / max(width_start, 1))

        if compression > 0.4:
            return PatternSignal(
                pattern_name="Симметричный треугольник",
                direction="wait",
                strength=0.65,
                timeframe="4h",
                description=f"Сжатие {compression:.0%}. Жди пробоя с объёмом — направление определит тренд.",
                stop_loss_pct=1.0,
                take_profit_pct=4.0,
            )
    return None


def detect_flag(df: pd.DataFrame) -> Optional[PatternSignal]:
    """Флаг — продолжение тренда после паузы."""
    if len(df) < 25:
        return None
    pole    = df.iloc[-25:-15]
    flag    = df.iloc[-15:]

    pole_move  = (pole["close"].iloc[-1] - pole["close"].iloc[0]) / pole["close"].iloc[0]
    flag_move  = (flag["close"].iloc[-1] - flag["close"].iloc[0]) / flag["close"].iloc[0]
    flag_range = (flag["high"].max() - flag["low"].min()) / flag["close"].mean()

    if abs(pole_move) > 0.05 and flag_range < 0.04 and abs(flag_move) < abs(pole_move) * 0.4:
        direction = "long" if pole_move > 0 else "short"
        return PatternSignal(
            pattern_name="Флаг (продолжение)",
            direction=direction,
            strength=0.75,
            timeframe="1h",
            description=f"Резкое движение {pole_move:+.1%} → консолидация. Ожидаем продолжение в том же направлении.",
            stop_loss_pct=1.2,
            take_profit_pct=4.5,
        )
    return None


# ══════════════════════════════════════════════════════════════════════════════
# INDICATORS
# ══════════════════════════════════════════════════════════════════════════════

def get_rsi(df: pd.DataFrame, period: int = 14) -> float:
    delta = df["close"].diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 1)


def get_trend(df: pd.DataFrame) -> str:
    ema9  = df["close"].ewm(span=9).mean().iloc[-1]
    ema21 = df["close"].ewm(span=21).mean().iloc[-1]
    ema50 = df["close"].ewm(span=50).mean().iloc[-1]
    c     = df["close"].iloc[-1]
    if c > ema9 > ema21 > ema50:
        return "strong_up"
    if c < ema9 < ema21 < ema50:
        return "strong_down"
    if c > ema21:
        return "up"
    if c < ema21:
        return "down"
    return "sideways"


# ══════════════════════════════════════════════════════════════════════════════
# MAIN SCAN — runs all detectors across multiple timeframes
# ══════════════════════════════════════════════════════════════════════════════

DETECTORS = [
    detect_hammer,
    detect_inverted_hammer,
    detect_engulfing,
    detect_doji,
    detect_morning_star,
    detect_shooting_star,
    detect_double_bottom,
    detect_double_top,
    detect_triangle,
    detect_flag,
]


def scan_all(df: pd.DataFrame) -> list[PatternSignal]:
    """Run all pattern detectors on a DataFrame. Returns found signals sorted by strength."""
    signals = []
    for detector in DETECTORS:
        try:
            sig = detector(df)
            if sig:
                signals.append(sig)
        except Exception:
            continue
    return sorted(signals, key=lambda s: s.strength, reverse=True)


def best_signal(df: pd.DataFrame) -> Optional[PatternSignal]:
    """Return the strongest actionable signal (not 'wait')."""
    signals = scan_all(df)
    for s in signals:
        if s.direction != "wait":
            return s
    return signals[0] if signals else None


def format_signal(sig: PatternSignal, rsi: float, trend: str) -> str:
    arrow = "▲ LONG" if sig.direction == "long" else ("▼ SHORT" if sig.direction == "short" else "◆ WAIT")
    return (
        f"{arrow} | {sig.pattern_name} | "
        f"Сила: {sig.strength:.0%} | TF: {sig.timeframe} | "
        f"RSI: {rsi} | Тренд: {trend} | "
        f"SL: -{sig.stop_loss_pct}% / TP: +{sig.take_profit_pct}%"
    )
