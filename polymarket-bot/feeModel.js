const config = require('./config');

function categoryFeeRate(category) {
    if (!category) return config.DEFAULT_TAKER_FEE_RATE;
    const key = category.toLowerCase();
    return config.TAKER_FEE_RATE_BY_CATEGORY[key] ?? config.DEFAULT_TAKER_FEE_RATE;
}

// fee = shares * feeRate * p * (1-p) — см. docs.polymarket.com/trading/fees
function takerFee(shares, price, feeRate) {
    const fee = shares * feeRate * price * (1 - price);
    return Math.max(fee, shares > 0 ? 0.00001 : 0);
}

module.exports = { categoryFeeRate, takerFee };
