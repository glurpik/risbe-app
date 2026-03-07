const sqlite3 = require('sqlite3').verbose();
const db = new sqlite3.Database('./risbe.db');

db.serialize(() => {
    db.run(`CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT DEFAULT 'user'
    )`);
});

module.exports = db;

// Добавь это в db.serialize в файле database.js
db.run(`CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender TEXT,
    receiver TEXT,
    text TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)`);

// УДАЛЕНИЕ ПОЛЬЗОВАТЕЛЯ (Админ-функция)
app.delete('/api/admin/user/:username', (req, res) => {
    const userToDelete = req.params.username;
    
    // Сначала удаляем сообщения этого пользователя, чтобы не забивать базу
    db.run(`DELETE FROM messages WHERE sender = ? OR receiver = ?`, [userToDelete, userToDelete]);
    
    // Затем удаляем самого пользователя
    db.run(`DELETE FROM users WHERE username = ?`, [userToDelete], function(err) {
        if (err) return res.status(500).json({ error: 'Ошибка БД' });
        res.json({ message: `Пользователь ${userToDelete} удален.` });
    });
});