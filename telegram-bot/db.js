const sqlite3 = require('sqlite3').verbose();
const path = require('path');

const db = new sqlite3.Database(path.join(__dirname, 'users.db'));

db.serialize(() => {
    db.run(`CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        free_used INTEGER DEFAULT 0,
        subscribed_until DATETIME
    )`);
});

function getUser(telegramId) {
    return new Promise((resolve, reject) => {
        db.get(`SELECT * FROM users WHERE telegram_id = ?`, [telegramId], (err, row) => (err ? reject(err) : resolve(row)));
    });
}

function upsertUser(telegramId, username) {
    return new Promise((resolve, reject) => {
        db.run(
            `INSERT INTO users (telegram_id, username) VALUES (?, ?)
             ON CONFLICT(telegram_id) DO UPDATE SET username = excluded.username`,
            [telegramId, username],
            (err) => (err ? reject(err) : resolve())
        );
    });
}

function incrementFreeUsed(telegramId) {
    return new Promise((resolve, reject) => {
        db.run(`UPDATE users SET free_used = free_used + 1 WHERE telegram_id = ?`, [telegramId], (err) => (err ? reject(err) : resolve()));
    });
}

function setSubscribed(telegramId, untilDate) {
    return new Promise((resolve, reject) => {
        db.run(`UPDATE users SET subscribed_until = ? WHERE telegram_id = ?`, [untilDate.toISOString(), telegramId], (err) => (err ? reject(err) : resolve()));
    });
}

function isSubscribed(user) {
    return !!(user && user.subscribed_until && new Date(user.subscribed_until) > new Date());
}

module.exports = { getUser, upsertUser, incrementFreeUsed, setSubscribed, isSubscribed };
