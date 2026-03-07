const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const sqlite3 = require('sqlite3').verbose();
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');

const app = express();
const server = http.createServer(app);
const io = new Server(server);
const db = new sqlite3.Database('./risbe.db');
const SECRET = 'RISBE_CEO_STRATEGY_2026';

app.use(express.json());
app.use(express.static('public'));

db.serialize(() => {
    db.run(`CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT)`);
    db.run(`CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT, receiver TEXT, text TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)`);
});

// Регистрация и Логин
app.post('/api/register', async (req, res) => {
    const { username, password } = req.body;
    if (!username || !password) return res.status(400).json({ error: 'Заполни все поля' });
    const hash = await bcrypt.hash(password, 10);
    db.run(`INSERT INTO users (username, password, role) VALUES (?, ?, ?)`, [username, hash, 'user'], (err) => {
        if (err) return res.status(400).json({ error: 'Этот ник уже занят' });
        res.json({ success: true });
    });
});

app.post('/api/login', (req, res) => {
    const { username, password } = req.body;
    db.get(`SELECT * FROM users WHERE username = ?`, [username], async (err, user) => {
        if (!user || !(await bcrypt.compare(password, user.password))) return res.status(401).json({ error: 'Неверный логин или пароль' });
        const token = jwt.sign({ username: user.username }, SECRET);
        res.json({ token, username: user.username });
    });
});

// Получение списка ВСЕХ пользователей (кроме себя)
app.get('/api/users', (req, res) => {
    const myName = req.query.me;
    db.all(`SELECT username FROM users WHERE username != ?`, [myName], (err, rows) => {
        res.json(rows || []);
    });
});

// Получение истории сообщений с конкретным человеком
app.get('/api/history', (req, res) => {
    const { me, withWho } = req.query;
    db.all(`SELECT * FROM messages WHERE (sender = ? AND receiver = ?) OR (sender = ? AND receiver = ?) ORDER BY timestamp ASC`, 
    [me, withWho, withWho, me], (err, rows) => {
        res.json(rows || []);
    });
});

// Socket.io Логика
io.on('connection', (socket) => {
    socket.on('join', (username) => {
        socket.join(username);
        console.log(`[LOG] ${username} подключился`);
    });

    socket.on('private_message', ({ sender, receiver, text }) => {
        if (!text.trim()) return;
        db.run(`INSERT INTO messages (sender, receiver, text) VALUES (?, ?, ?)`, [sender, receiver, text], function(err) {
            // Отправляем сообщение получателю
            io.to(receiver).emit('new_message', { sender, text });
        });
    });
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => console.log(`RisBe PRO запущен на порту ${PORT}`));