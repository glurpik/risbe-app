"""Polymarket CLOB integration."""

from typing import List, Optional
from dataclasses import dataclass

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import OrderArgs, OrderType, Side
    CLOB_AVAILABLE = True
except ImportError:
    CLOB_AVAILABLE = False

from config import POLYMARKET_API_KEY, POLYMARKET_SECRET, POLYMARKET_PASSPHRASE


@dataclass
class Market:
    id: str
    question: str
    yes_price: float
    no_price: float
    volume: float
    active: bool


_client: Optional["ClobClient"] = None


def _get_client():
    global _client
    if not CLOB_AVAILABLE:
        raise RuntimeError("py-clob-client not installed")
    if _client is None:
        _client = ClobClient(
            host="https://clob.polymarket.com",
            key=POLYMARKET_API_KEY,
            secret=POLYMARKET_SECRET,
            passphrase=POLYMARKET_PASSPHRASE,
            chain_id=137,
        )
    return _client


def get_active_markets(limit: int = 30) -> List[Market]:
    if not CLOB_AVAILABLE or not POLYMARKET_API_KEY:
        return _mock_markets()
    try:
        client = _get_client()
        resp = client.get_markets()
        markets = []
        for m in (resp.get("data") or [])[:limit]:
            try:
                tokens = m.get("tokens", [])
                yes_price = float(tokens[0].get("price", 0.5)) if tokens else 0.5
                markets.append(Market(
                    id=m["condition_id"],
                    question=m.get("question", ""),
                    yes_price=yes_price,
                    no_price=round(1 - yes_price, 4),
                    volume=float(m.get("volume", 0)),
                    active=m.get("active", False),
                ))
            except Exception:
                continue
        return markets
    except Exception as e:
        print(f"[Polymarket] API error: {e}")
        return _mock_markets()


def place_order(market_id: str, side: str, amount_usdc: float) -> dict:
    if not CLOB_AVAILABLE or not POLYMARKET_API_KEY:
        return {"status": "mock", "market": market_id, "side": side, "amount": amount_usdc}
    try:
        client = _get_client()
        order_side = Side.BUY if side == "YES" else Side.SELL
        args = OrderArgs(
            token_id=market_id,
            price=0.5,
            size=amount_usdc,
            side=order_side,
        )
        resp = client.create_and_post_order(args)
        return {"status": "ok", "order_id": resp.get("orderID"), "market": market_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _mock_markets() -> List[Market]:
    return [
        Market("mock-001", "Will BTC exceed $100k by end of 2025?", 0.72, 0.28, 50000, True),
        Market("mock-002", "Will there be a US recession in 2025?",  0.35, 0.65, 120000, True),
        Market("mock-003", "Will Fed cut rates in June 2025?",        0.58, 0.42, 80000, True),
    ]
