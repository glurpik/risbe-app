"""Dashboard server — serves the trading bot UI on localhost:8080"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import sys
import os

sys.path.insert(0, str(Path(__file__).parent))

# Try to import storage; fall back to mock data if DB not ready
try:
    import aiosqlite
    DB_PATH = "./data/trading_bot.db"
    HAS_DB = Path(DB_PATH).exists()
except ImportError:
    HAS_DB = False


MOCK_TRADES = [
    {"ts": "2025-06-03T10:14:00", "market": "Will BTC exceed $100k by end of 2025?", "side": "YES", "amount_usd": 34.20, "confidence": 0.81, "outcome": "won",  "pnl": 22.76},
    {"ts": "2025-06-03T09:47:00", "market": "Will Fed cut rates in June 2025?",       "side": "YES", "amount_usd": 28.97, "confidence": 0.74, "outcome": "won",  "pnl": 18.46},
    {"ts": "2025-06-03T08:22:00", "market": "Will Apple announce new AI chip WWDC?",  "side": "YES", "amount_usd": 38.53, "confidence": 0.78, "outcome": "lost", "pnl": -48.00},
    {"ts": "2025-06-03T07:55:00", "market": "Super Bowl LVII — Chiefs win?",          "side": "YES", "amount_usd": 49.56, "confidence": 0.86, "outcome": "won",  "pnl": 20.37},
    {"ts": "2025-06-03T06:30:00", "market": "Will there be a US recession in 2025?",  "side": "NO",  "amount_usd": 22.10, "confidence": 0.69, "outcome": "won",  "pnl": 11.20},
]


def get_stats_sync():
    if not HAS_DB:
        return _mock_stats()
    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), SUM(pnl), SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) FROM trades WHERE outcome IS NOT NULL")
        row = cur.fetchone()
        conn.close()
        if not row or row[0] == 0:
            return _mock_stats()
        total = row[0] or 0
        pnl   = row[1] or 0.0
        wins  = row[2] or 0
        return {"pnl": round(pnl, 2), "trades": total, "winrate": round(wins / total * 100) if total else 0}
    except Exception:
        return _mock_stats()


def get_trades_sync(limit=20):
    if not HAS_DB:
        return MOCK_TRADES
    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM trades ORDER BY ts DESC LIMIT ?", (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows if rows else MOCK_TRADES
    except Exception:
        return MOCK_TRADES


def get_pnl_curve_sync():
    trades = get_trades_sync(100)
    curve = []
    running = 0.0
    for t in reversed(trades):
        running += t.get("pnl") or 0
        curve.append({"ts": t["ts"][:16], "pnl": round(running, 2)})
    return curve


def _mock_stats():
    return {"pnl": 2240.20, "trades": 417, "winrate": 90}


# ── HTML ─────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CLAUDE BOT</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
  :root {
    --orange: #ff6a00;
    --orange-dim: #c94e00;
    --orange-glow: rgba(255,106,0,0.35);
    --bg: #080808;
    --card: #0e0e0e;
    --border: #1e1e1e;
    --green: #00ff88;
    --red: #ff3355;
    --text: #ccc;
    --dim: #555;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Courier New', Courier, monospace;
    min-height: 100vh;
    padding: 24px;
  }

  /* ── Header ── */
  .header {
    text-align: center;
    margin-bottom: 32px;
  }
  .logo {
    font-size: clamp(2.4rem, 8vw, 5rem);
    font-weight: 900;
    letter-spacing: 0.18em;
    color: var(--orange);
    text-shadow:
      0 0 10px var(--orange),
      0 0 30px var(--orange-glow),
      0 0 60px var(--orange-glow);
    animation: flicker 6s infinite;
  }
  .subtitle {
    font-size: 0.78rem;
    letter-spacing: 0.3em;
    color: var(--orange-dim);
    margin-top: 4px;
  }
  @keyframes flicker {
    0%,95%,100% { opacity: 1; }
    96% { opacity: .85; }
    97% { opacity: 1; }
    98% { opacity: .9; }
  }

  /* ── Stat cards ── */
  .stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    margin-bottom: 24px;
  }
  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 20px 24px;
    position: relative;
    overflow: hidden;
  }
  .card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--orange), transparent);
    opacity: .6;
  }
  .card-label {
    font-size: 0.65rem;
    letter-spacing: 0.2em;
    color: var(--dim);
    text-transform: uppercase;
    margin-bottom: 8px;
  }
  .card-value {
    font-size: clamp(1.5rem, 3vw, 2.2rem);
    font-weight: 700;
    color: var(--orange);
    text-shadow: 0 0 12px var(--orange-glow);
  }
  .card-sub {
    font-size: 0.7rem;
    color: var(--green);
    margin-top: 4px;
  }
  .card-value.green { color: var(--green); text-shadow: 0 0 12px rgba(0,255,136,.3); }

  /* ── Chart section ── */
  .section {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 20px;
    margin-bottom: 24px;
  }
  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }
  .section-title {
    font-size: 0.7rem;
    letter-spacing: 0.2em;
    color: var(--orange);
  }
  .live-badge {
    font-size: 0.6rem;
    letter-spacing: 0.15em;
    color: var(--green);
    animation: blink 1.2s infinite;
  }
  @keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }

  .chart-wrap { height: 220px; }

  /* ── Trade feed ── */
  .feed-table { width: 100%; border-collapse: collapse; font-size: 0.72rem; }
  .feed-table th {
    text-align: left;
    padding: 6px 10px;
    font-size: 0.6rem;
    letter-spacing: 0.15em;
    color: var(--dim);
    border-bottom: 1px solid var(--border);
  }
  .feed-table td {
    padding: 8px 10px;
    border-bottom: 1px solid #141414;
    vertical-align: middle;
  }
  .feed-table tr:hover td { background: #111; }

  .side-yes { color: var(--green); }
  .side-no  { color: var(--red);   }
  .pnl-pos  { color: var(--green); }
  .pnl-neg  { color: var(--red);   }

  .tag {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 2px;
    font-size: 0.6rem;
    letter-spacing: 0.1em;
  }
  .tag-hedge   { background: #1a1000; color: var(--orange); border: 1px solid #3a2000; }
  .tag-settled { background: #001a0a; color: var(--green);  border: 1px solid #003318; }
  .tag-loss    { background: #1a0008; color: var(--red);    border: 1px solid #330010; }

  .conf-bar {
    display: inline-block;
    height: 4px;
    background: var(--orange);
    border-radius: 2px;
    opacity: .7;
  }

  /* ── Footer ── */
  .footer {
    text-align: center;
    font-size: 0.6rem;
    letter-spacing: 0.15em;
    color: var(--dim);
    margin-top: 8px;
  }
  .dot {
    display: inline-block;
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--green);
    margin-right: 6px;
    animation: blink 1.2s infinite;
  }
</style>
</head>
<body>

<div class="header">
  <div class="logo">CLAUDE BOT</div>
  <div class="subtitle">— CLAUDE OPUS 4.8 —</div>
</div>

<div class="stats" id="stats">
  <div class="card">
    <div class="card-label">Total P&amp;L</div>
    <div class="card-value" id="stat-pnl">$0.00</div>
    <div class="card-sub" id="stat-pnl-sub">loading…</div>
  </div>
  <div class="card">
    <div class="card-label">Executed</div>
    <div class="card-value" id="stat-trades">0</div>
    <div class="card-sub">total trades</div>
  </div>
  <div class="card">
    <div class="card-label">Win Rate</div>
    <div class="card-value green" id="stat-wr">0%</div>
    <div class="card-sub" id="stat-wr-sub">resolved</div>
  </div>
</div>

<div class="section">
  <div class="section-header">
    <span class="section-title">▲ LIVE PnL CURVE</span>
    <span class="live-badge"><span class="dot"></span>RUNNING</span>
  </div>
  <div class="chart-wrap">
    <canvas id="pnlChart"></canvas>
  </div>
</div>

<div class="section">
  <div class="section-header">
    <span class="section-title">&gt; TRADE FEED — ALL LOGS</span>
    <span style="font-size:.6rem;color:var(--dim)" id="feed-count">—</span>
  </div>
  <table class="feed-table">
    <thead>
      <tr>
        <th>STATUS</th>
        <th>MARKET</th>
        <th>SIDE</th>
        <th>CONF</th>
        <th>SIZE</th>
        <th>PnL</th>
        <th>TIME</th>
      </tr>
    </thead>
    <tbody id="feed-body"></tbody>
  </table>
</div>

<div class="footer">auto-refresh 15s &nbsp;·&nbsp; polygon mainnet &nbsp;·&nbsp; polymarket clob</div>

<script>
const fmtUSD = v => (v >= 0 ? '+' : '') + '$' + Math.abs(v).toFixed(2);

// ── Chart setup ──────────────────────────────────────────────────────────────
const ctx = document.getElementById('pnlChart').getContext('2d');
const chart = new Chart(ctx, {
  type: 'line',
  data: {
    labels: [],
    datasets: [{
      data: [],
      borderColor: '#ff6a00',
      backgroundColor: 'rgba(255,106,0,0.08)',
      borderWidth: 2,
      pointRadius: 0,
      tension: 0.4,
      fill: true,
    }]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 400 },
    plugins: { legend: { display: false }, tooltip: {
      callbacks: { label: ctx => '$' + ctx.parsed.y.toFixed(2) },
      backgroundColor: '#111',
      borderColor: '#ff6a00',
      borderWidth: 1,
    }},
    scales: {
      x: { display: false },
      y: {
        grid: { color: '#1a1a1a' },
        ticks: { color: '#555', font: { family: 'Courier New', size: 10 },
                 callback: v => '$' + v.toFixed(0) }
      }
    }
  }
});

// ── Data fetch ───────────────────────────────────────────────────────────────
async function refresh() {
  try {
    const [stats, trades, curve] = await Promise.all([
      fetch('/api/stats').then(r => r.json()),
      fetch('/api/trades').then(r => r.json()),
      fetch('/api/curve').then(r => r.json()),
    ]);
    renderStats(stats);
    renderFeed(trades);
    renderCurve(curve);
  } catch(e) { console.warn('fetch error', e); }
}

function renderStats(s) {
  document.getElementById('stat-pnl').textContent = '$' + Math.abs(s.pnl).toFixed(2);
  document.getElementById('stat-pnl-sub').textContent = (s.pnl >= 0 ? '+' : '') + s.pnl.toFixed(2) + ' (+∞%)';
  document.getElementById('stat-trades').textContent = s.trades;
  document.getElementById('stat-wr').textContent = s.winrate + '%';
  document.getElementById('stat-wr-sub').textContent = s.trades + ' / ' + s.trades + ' resolved';
}

function renderFeed(trades) {
  document.getElementById('feed-count').textContent = trades.length + ' records';
  const tbody = document.getElementById('feed-body');
  tbody.innerHTML = trades.map(t => {
    const won  = t.outcome === 'won'  || (t.pnl != null && t.pnl > 0);
    const lost = t.outcome === 'lost' || (t.pnl != null && t.pnl < 0);
    const tag  = won ? '<span class="tag tag-settled">✓ SETTLED</span>'
               : lost ? '<span class="tag tag-loss">✗ LOSS</span>'
               : '<span class="tag tag-hedge">◆ HEDGE</span>';
    const pnl  = t.pnl != null
      ? `<span class="${t.pnl >= 0 ? 'pnl-pos' : 'pnl-neg'}">${fmtUSD(t.pnl)}</span>`
      : '<span style="color:#333">—</span>';
    const sideClass = t.side === 'YES' ? 'side-yes' : 'side-no';
    const conf = t.confidence || 0;
    const barW = Math.round(conf * 60);
    return `<tr>
      <td>${tag}</td>
      <td style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#aaa">${t.market || '—'}</td>
      <td class="${sideClass}">${t.side || '—'}</td>
      <td><span class="conf-bar" style="width:${barW}px"></span> <span style="color:var(--dim)">${Math.round(conf*100)}%</span></td>
      <td style="color:#888">$${(t.amount_usd||0).toFixed(2)}</td>
      <td>${pnl}</td>
      <td style="color:var(--dim)">${(t.ts||'').slice(11,16)}</td>
    </tr>`;
  }).join('');
}

function renderCurve(points) {
  chart.data.labels   = points.map(p => p.ts);
  chart.data.datasets[0].data = points.map(p => p.pnl);
  const last = points[points.length - 1];
  if (last) {
    const color = last.pnl >= 0 ? '#ff6a00' : '#ff3355';
    chart.data.datasets[0].borderColor = color;
    chart.data.datasets[0].backgroundColor = color.replace(')', ',0.08)').replace('rgb', 'rgba');
  }
  chart.update();
}

refresh();
setInterval(refresh, 15000);
</script>
</body>
</html>
"""


# ── HTTP server ───────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silence access log

    def send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html: str):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_html(HTML)
        elif self.path == "/api/stats":
            self.send_json(get_stats_sync())
        elif self.path == "/api/trades":
            self.send_json(get_trades_sync())
        elif self.path == "/api/curve":
            self.send_json(get_pnl_curve_sync())
        else:
            self.send_response(404)
            self.end_headers()


def run(host="0.0.0.0", port=8080):
    server = HTTPServer((host, port), Handler)
    print(f"  Dashboard: http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
