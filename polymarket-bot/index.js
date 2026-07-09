const config = require('./config');
const { fetchActiveMarkets, fetchOrderBook } = require('./polymarketClient');
const { findArbitrage } = require('./arbitrage');
const db = require('./db');

let bankroll = config.STARTING_BANKROLL;
let running = true;
let scanOffset = 0;

function log(msg) {
    const ts = new Date().toISOString();
    console.log(`[${ts}] ${msg}`);
}

async function scanOnce() {
    let markets;
    try {
        const result = await fetchActiveMarkets(config.MAX_MARKETS_TRACKED, scanOffset);
        markets = result.markets;
        scanOffset = result.nextOffset;
    } catch (err) {
        log(`ERROR fetching markets: ${err.message}`);
        return;
    }
    log(`Scanning ${markets.length} liquid binary markets (offset ${scanOffset})...`);

    let found = 0;
    for (const m of markets) {
        if (!running) break;
        let tokenIds;
        try {
            tokenIds = typeof m.clobTokenIds === 'string' ? JSON.parse(m.clobTokenIds) : m.clobTokenIds;
        } catch {
            continue;
        }
        if (!tokenIds || tokenIds.length !== 2) continue;
        const [yesTokenId, noTokenId] = tokenIds;
        const conditionId = m.conditionId || m.id;

        let alreadyUsed = 0;
        try {
            alreadyUsed = await db.getExposure(conditionId);
        } catch (err) {
            log(`ERROR reading exposure: ${err.message}`);
        }
        const remainingCap = config.MAX_CUMULATIVE_SHARES_PER_MARKET - alreadyUsed;
        if (remainingCap <= 0) continue;

        let yesBook, noBook;
        try {
            [yesBook, noBook] = await Promise.all([fetchOrderBook(yesTokenId), fetchOrderBook(noTokenId)]);
        } catch (err) {
            continue; // тихо пропускаем — сеть/рейт-лимиты, не критично для эксперимента
        }

        const opp = findArbitrage({
            market: { conditionId, question: m.question, category: m.category },
            yesBook,
            noBook,
            remainingCap,
            bankroll,
        });

        if (opp && opp.cost <= bankroll) {
            bankroll -= opp.cost + opp.gasEst;
            bankroll += opp.shares * 1; // merge complete set -> $1 USDC мгновенно
            found += 1;
            try {
                await db.addExposure(conditionId, opp.shares);
                await db.recordTrade({ ...opp, bankrollAfter: bankroll });
            } catch (err) {
                log(`ERROR recording trade: ${err.message}`);
            }
            log(`ARBITRAGE: "${opp.question.slice(0, 60)}" shares=${opp.shares.toFixed(2)} cost=$${opp.cost.toFixed(2)} netProfit=$${opp.netProfit.toFixed(4)} bankroll=$${bankroll.toFixed(2)}`);
        }
    }

    const summary = await db.getSummary();
    await db.recordSnapshot({
        bankroll,
        totalTrades: summary.totalTrades,
        totalNetProfit: summary.totalNetProfit,
        marketsScanned: markets.length,
    });
    log(`Scan done. Opportunities this pass: ${found}. Bankroll: $${bankroll.toFixed(2)}. Total trades so far: ${summary.totalTrades}.`);
}

async function loop() {
    while (running) {
        const start = Date.now();
        await scanOnce();
        const elapsed = Date.now() - start;
        const wait = Math.max(config.SCAN_INTERVAL_MS - elapsed, 2000);
        await new Promise((r) => setTimeout(r, wait));
    }
}

process.on('SIGINT', () => { running = false; log('Stopping...'); process.exit(0); });
process.on('SIGTERM', () => { running = false; log('Stopping...'); process.exit(0); });

log(`Paper-trading arbitrage bot started. Starting bankroll: $${bankroll.toFixed(2)} (virtual, no real funds).`);
loop();
