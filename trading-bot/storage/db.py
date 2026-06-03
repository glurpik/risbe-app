import aiosqlite
import json
from datetime import datetime
from pathlib import Path

from config import SQLITE_PATH


async def init_db():
    Path(SQLITE_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(SQLITE_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                market TEXT NOT NULL,
                side TEXT NOT NULL,
                amount_usd REAL NOT NULL,
                confidence REAL NOT NULL,
                outcome TEXT,
                pnl REAL,
                metadata TEXT
            );

            CREATE TABLE IF NOT EXISTS news_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                lang TEXT
            );

            CREATE TABLE IF NOT EXISTS calibration (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                predicted_outcome TEXT NOT NULL,
                actual_outcome TEXT,
                confidence REAL NOT NULL,
                market TEXT NOT NULL
            );
        """)
        await db.commit()


async def log_trade(market: str, side: str, amount_usd: float, confidence: float, metadata: dict = None):
    async with aiosqlite.connect(SQLITE_PATH) as db:
        await db.execute(
            "INSERT INTO trades (ts, market, side, amount_usd, confidence, metadata) VALUES (?,?,?,?,?,?)",
            (datetime.utcnow().isoformat(), market, side, amount_usd, confidence, json.dumps(metadata or {}))
        )
        await db.commit()


async def update_trade_outcome(trade_id: int, outcome: str, pnl: float):
    async with aiosqlite.connect(SQLITE_PATH) as db:
        await db.execute(
            "UPDATE trades SET outcome=?, pnl=? WHERE id=?",
            (outcome, pnl, trade_id)
        )
        await db.commit()


async def log_calibration(market: str, predicted: str, confidence: float):
    async with aiosqlite.connect(SQLITE_PATH) as db:
        await db.execute(
            "INSERT INTO calibration (ts, predicted_outcome, confidence, market) VALUES (?,?,?,?)",
            (datetime.utcnow().isoformat(), predicted, confidence, market)
        )
        await db.commit()


async def get_recent_trades(limit: int = 50) -> list:
    async with aiosqlite.connect(SQLITE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM trades ORDER BY ts DESC LIMIT ?", (limit,)
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_calibration_stats() -> dict:
    async with aiosqlite.connect(SQLITE_PATH) as db:
        async with db.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN predicted_outcome = actual_outcome THEN 1 ELSE 0 END) as correct,
                AVG(confidence) as avg_confidence
            FROM calibration
            WHERE actual_outcome IS NOT NULL
        """) as cursor:
            row = await cursor.fetchone()
            if not row or row[0] == 0:
                return {"total": 0, "accuracy": 0.0, "avg_confidence": 0.0}
            return {
                "total": row[0],
                "accuracy": (row[1] or 0) / row[0],
                "avg_confidence": row[2] or 0.0,
            }
