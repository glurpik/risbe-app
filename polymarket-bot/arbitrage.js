const config = require('./config');
const { categoryFeeRate, takerFee } = require('./feeModel');

function parseLevels(book) {
    if (!book || !Array.isArray(book.asks)) return [];
    return book.asks
        .map((l) => ({ price: parseFloat(l.price), size: parseFloat(l.size) }))
        .filter((l) => l.price > 0 && l.size > 0)
        .sort((a, b) => a.price - b.price);
}

// Ищет прибыльный "complete set" арбитраж: купить YES+NO дешевле $1 суммарно,
// сразу смёржить в $1 USDC (реальный механизм Gnosis conditional tokens на Polymarket).
// Идём по стакану шаг за шагом, пока предельный эдж не упадёт ниже порога.
function findArbitrage({ market, yesBook, noBook, remainingCap, bankroll }) {
    const feeRate = categoryFeeRate(market.category);
    const yesLevels = parseLevels(yesBook);
    const noLevels = parseLevels(noBook);
    if (yesLevels.length === 0 || noLevels.length === 0) return null;

    let yi = 0, ni = 0;
    let yRemaining = yesLevels[0]?.size ?? 0;
    let nRemaining = noLevels[0]?.size ?? 0;

    let totalShares = 0;
    let totalCost = 0;
    let totalFee = 0;

    const notionalCap = bankroll * config.MAX_NOTIONAL_FRACTION_OF_BANKROLL;
    let hardCap = Math.min(config.MAX_SHARES_PER_TRADE, remainingCap);

    while (yi < yesLevels.length && ni < noLevels.length && totalShares < hardCap) {
        const yPrice = yesLevels[yi].price;
        const nPrice = noLevels[ni].price;
        const grossEdge = 1 - yPrice - nPrice;
        const marginalFee = takerFee(1, yPrice, feeRate) + takerFee(1, nPrice, feeRate);
        const netEdge = grossEdge - marginalFee;

        if (netEdge < config.MIN_NET_EDGE_PER_SHARE) break;

        let step = Math.min(yRemaining, nRemaining, hardCap - totalShares);
        // не позволяем одному шагу пробить лимит по капиталу
        const notionalPerShare = yPrice + nPrice;
        const maxByNotional = notionalPerShare > 0 ? (notionalCap - totalCost) / notionalPerShare : 0;
        step = Math.min(step, Math.max(maxByNotional, 0));
        if (step <= 0) break;

        totalShares += step;
        totalCost += step * (yPrice + nPrice);
        totalFee += takerFee(step, yPrice, feeRate) + takerFee(step, nPrice, feeRate);

        yRemaining -= step;
        nRemaining -= step;
        if (yRemaining <= 1e-9) { yi += 1; yRemaining = yesLevels[yi]?.size ?? 0; }
        if (nRemaining <= 1e-9) { ni += 1; nRemaining = noLevels[ni]?.size ?? 0; }
    }

    if (totalShares <= 0) return null;

    const grossPayout = totalShares * 1;
    const netProfit = grossPayout - totalCost - totalFee - config.GAS_ESTIMATE_USD;
    if (netProfit <= 0) return null;

    return {
        conditionId: market.conditionId,
        question: market.question,
        category: market.category,
        askYes: yesLevels[0].price,
        askNo: noLevels[0].price,
        shares: totalShares,
        cost: totalCost,
        feeYes: totalFee / 2, // приблизительный сплит для лога
        feeNo: totalFee / 2,
        gasEst: config.GAS_ESTIMATE_USD,
        netProfit,
    };
}

module.exports = { findArbitrage };
