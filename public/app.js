const socket = io();
let currentUser = localStorage.getItem('username');
let chatPartner = null;

if (currentUser) {
    socket.emit('join', currentUser);
    showScreen('feed');
}

async function handleAuth(type) {
    const u = document.getElementById('login-user').value;
    const p = document.getElementById('login-pass').value;
    const res = await fetch(`/api/${type}`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username: u, password: p})
    });
    const data = await res.json();
    if (res.ok) {
        if (type === 'login') {
            localStorage.setItem('username', data.username);
            location.reload();
        } else alert('Успех! Теперь входи.');
    } else alert(data.error);
}

function showScreen(screen) {
    document.querySelectorAll('.card').forEach(s => s.classList.add('hidden'));
    document.getElementById(`screen-${screen}`).classList.remove('hidden');
    if (screen === 'feed') loadUsers();
}

async function loadUsers() {
    document.getElementById('my-nick').innerText = `Вы: ${currentUser}`;
    const res = await fetch(`/api/users?me=${currentUser}`);
    const users = await res.json();
    const list = document.getElementById('user-list');
    list.innerHTML = users.length ? '' : '<p>Пока никого нет...</p>';
    
    users.forEach(u => {
        const btn = document.createElement('div');
        btn.className = 'user-card';
        btn.innerHTML = `<span>👤 ${u.username}</span> <button onclick="openChat('${u.username}')">Чат</button>`;
        list.appendChild(btn);
    });
}

async function openChat(name) {
    chatPartner = name;
    document.getElementById('chat-with-title').innerText = `Чат с ${name}`;
    document.getElementById('chat-window').innerHTML = '<p style="text-align:center">Загрузка истории...</p>';
    showScreen('chat');

    // Загружаем историю из БД
    const res = await fetch(`/api/history?me=${currentUser}&withWho=${name}`);
    const messages = await res.json();
    document.getElementById('chat-window').innerHTML = '';
    messages.forEach(m => appendMessage(m.sender === currentUser ? 'Вы' : m.sender, m.text));
}

function sendPrivateMsg() {
    const input = document.getElementById('chat-msg');
    if (!input.value.trim()) return;
    
    socket.emit('private_message', { sender: currentUser, receiver: chatPartner, text: input.value });
    appendMessage('Вы', input.value);
    input.value = '';
}

socket.on('new_message', (data) => {
    if (chatPartner === data.sender) {
        appendMessage(data.sender, data.text);
    } else {
        // Уведомление, если чат с этим человеком сейчас не открыт
        alert(`Сообщение от ${data.sender}: ${data.text}`);
        if (document.getElementById('screen-feed').classList.contains('hidden') === false) {
            loadUsers(); // Обновить ленту
        }
    }
});

function appendMessage(sender, text) {
    const win = document.getElementById('chat-window');
    const div = document.createElement('div');
    div.className = sender === 'Вы' ? 'msg-own' : 'msg-partner';
    div.innerHTML = `<b>${sender}:</b> ${text}`;
    win.appendChild(div);
    win.scrollTop = win.scrollHeight;
}

function logout() { localStorage.clear(); location.reload(); }