"""
Bybit integration via ccxt.
Fetches OHLCV candles for pattern detection + places spot orders.
"""

from typing import Optional
import pandas as pd

try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False

from config import BYBIT_API_KEY, BYBIT_SECRET


_exchange: Optional["ccxt.bybit"] = None


def _get_exchange():
    global _exchange
    if not CCXT_AVAILABLE:
        raise RuntimeError("ccxt not installed — run: pip install ccxt")
    if _exchange is None:
        _exchange = ccxt.bybit({
            "apiKey": BYBIT_API_KEY,
            "secret": BYBIT_SECRET,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
    return _exchange


def get_candles(symbol: str = "BTC/USDT", timeframe: str = "1h", limit: int = 100) -> pd.DataFrame:
    """Fetch OHLCV candles. Works without API keys (public endpoint)."""
    try:
        ex = _get_exchange()
    except Exception:
        # no API keys — use public REST directly
        import requests
        tf_map = {"15m": "15", "1h": "60", "4h": "240", "1d": "D"}
        tf = tf_map.get(timeframe, "60")
        sym = symbol.replace("/", "")
        url = f"https://api.bybit.com/v5/market/kline?category=spot&symbol={sym}&interval={tf}&limit={limit}"
        r = requests.get(url, timeout=10).json()
        rows = r.get("result", {}).get("list", [])
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume", "turnover"])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        df["ts"] = pd.to_datetime(df["ts"].astype(float), unit="ms")
        return df.iloc[::-1].reset_index(drop=True)

    ohlcv = ex.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    return df


def get_price(symbol: str = "BTC/USDT") -> float:
    try:
        ex = _get_exchange()
        ticker = ex.fetch_ticker(symbol)
        return float(ticker["last"])
    except Exception:
        import requests
        sym = symbol.replace("/", "")
        r = requests.get(f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={sym}", timeout=8).json()
        return float(r["result"]["list"][0]["lastPrice"])


def place_order(symbol: str, side: str, usdt_amount: float) -> dict:
    """side: 'buy' or 'sell'. Returns order dict."""
    if not BYBIT_API_KEY:
        price = get_price(symbol)
        qty = round(usdt_amount / price, 6)
        return {"status": "mock", "symbol": symbol, "side": side, "qty": qty, "price": price}
    try:
        ex = _get_exchange()
        price = get_price(symbol)
        qty = round(usdt_amount / price, 6)
        order = ex.create_order(symbol, "market", side, qty)
        return {"status": "ok", "order_id": order["id"], "symbol": symbol, "side": side, "qty": qty, "price": price}
    except Exception as e:
        return {"status": "error", "message": str(e)}
