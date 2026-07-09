const sqlite3 = require('sqlite3').verbose();
const path = require('path');

const db = new sqlite3.Database(path.join(__dirname, 'paper_trades.db'));

db.serialize(() => {
    db.run(`CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        condition_id TEXT,
        question TEXT,
        category TEXT,
        ask_yes REAL,
        ask_no REAL,
        shares REAL,
        cost REAL,
        fee_yes REAL,
        fee_no REAL,
        gas_est REAL,
        net_profit REAL,
        bankroll_after REAL
    )`);

    db.run(`CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        bankroll REAL,
        total_trades INTEGER,
        total_net_profit REAL,
        markets_scanned INTEGER,
        note TEXT
    )`);

    db.run(`CREATE TABLE IF NOT EXISTS market_exposure (
        condition_id TEXT PRIMARY KEY,
        cumulative_shares REAL DEFAULT 0
    )`);
});

function recordTrade(trade) {
    return new Promise((resolve, reject) => {
        db.run(
            `INSERT INTO trades (condition_id, question, category, ask_yes, ask_no, shares, cost, fee_yes, fee_no, gas_est, net_profit, bankroll_after)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
            [trade.conditionId, trade.question, trade.category, trade.askYes, trade.askNo, trade.shares, trade.cost,
             trade.feeYes, trade.feeNo, trade.gasEst, trade.netProfit, trade.bankrollAfter],
            function (err) {
                if (err) return reject(err);
                resolve(this.lastID);
            }
        );
    });
}

function getExposure(conditionId) {
    return new Promise((resolve, reject) => {
        db.get(`SELECT cumulative_shares FROM market_exposure WHERE condition_id = ?`, [conditionId], (err, row) => {
            if (err) return reject(err);
            resolve(row ? row.cumulative_shares : 0);
        });
    });
}

function addExposure(conditionId, shares) {
    return new Promise((resolve, reject) => {
        db.run(
            `INSERT INTO market_exposure (condition_id, cumulative_shares) VALUES (?, ?)
             ON CONFLICT(condition_id) DO UPDATE SET cumulative_shares = cumulative_shares + excluded.cumulative_shares`,
            [conditionId, shares],
            (err) => (err ? reject(err) : resolve())
        );
    });
}

function recordSnapshot(snapshot) {
    return new Promise((resolve, reject) => {
        db.run(
            `INSERT INTO snapshots (bankroll, total_trades, total_net_profit, markets_scanned, note) VALUES (?, ?, ?, ?, ?)`,
            [snapshot.bankroll, snapshot.totalTrades, snapshot.totalNetProfit, snapshot.marketsScanned, snapshot.note || null],
            (err) => (err ? reject(err) : resolve())
        );
    });
}

function getSummary() {
    return new Promise((resolve, reject) => {
        db.get(
            `SELECT COUNT(*) as totalTrades, COALESCE(SUM(net_profit),0) as totalNetProfit FROM trades`,
            [],
            (err, row) => (err ? reject(err) : resolve(row))
        );
    });
}

module.exports = { db, recordTrade, getExposure, addExposure, recordSnapshot, getSummary };
