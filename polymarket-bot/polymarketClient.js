const config = require('./config');

async function fetchJson(url, attempt = 1) {
    const res = await fetch(url);
    if (res.status === 429 && attempt <= 4) {
        const wait = attempt * 1000;
        await new Promise((r) => setTimeout(r, wait));
        return fetchJson(url, attempt + 1);
    }
    if (!res.ok) {
        throw new Error(`${res.status} ${res.statusText} for ${url}`);
    }
    return res.json();
}

// Активные бинарные рынки с достаточной ликвидностью.
// startOffset позволяет ротировать окно между вызовами: топ по объёму уже
// разобран проф-ботами за секунды, длинный хвост менее заметных рынков —
// более вероятное место для отстающего прайсинга.
async function fetchActiveMarkets(limit, startOffset = 0) {
    const markets = [];
    let offset = startOffset;
    let sawEnd = false;
    while (markets.length < limit) {
        const url = `${config.GAMMA_BASE}/markets?active=true&closed=false&limit=${config.MARKETS_PAGE_SIZE}&offset=${offset}&order=id&ascending=true`;
        const page = await fetchJson(url);
        if (!Array.isArray(page) || page.length === 0) { sawEnd = true; break; }
        markets.push(...page);
        offset += page.length;
        if (page.length < config.MARKETS_PAGE_SIZE) { sawEnd = true; break; }
    }
    const filtered = markets
        .filter((m) => {
            const liquidity = parseFloat(m.liquidityNum ?? m.liquidity ?? '0');
            let tokenIds = [];
            try {
                tokenIds = typeof m.clobTokenIds === 'string' ? JSON.parse(m.clobTokenIds) : (m.clobTokenIds || []);
            } catch {
                tokenIds = [];
            }
            return liquidity >= config.MIN_LIQUIDITY_USD && tokenIds.length === 2 && !m.negRisk;
        })
        .slice(0, limit);
    return { markets: filtered, nextOffset: sawEnd ? 0 : offset };
}

async function fetchOrderBook(tokenId) {
    const url = `${config.CLOB_BASE}/book?token_id=${tokenId}`;
    return fetchJson(url);
}

module.exports = { fetchActiveMarkets, fetchOrderBook };
