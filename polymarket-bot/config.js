module.exports = {
    // Виртуальный банкролл эксперимента. Реальные деньги нигде не участвуют.
    STARTING_BANKROLL: 1000,

    GAMMA_BASE: 'https://gamma-api.polymarket.com',
    CLOB_BASE: 'https://clob.polymarket.com',

    SCAN_INTERVAL_MS: 20_000,
    MARKETS_PAGE_SIZE: 100,
    // Сколько активных рынков держим в ротации сканирования
    MAX_MARKETS_TRACKED: 150,
    // Не трогаем рынки с низкой ликвидностью — там "арбитраж" это мираж из пустого стакана
    MIN_LIQUIDITY_USD: 300,

    // Минимальный эдж после комиссий и газа, ниже которого сделку не берём
    MIN_NET_EDGE_PER_SHARE: 0.005,

    // Ограничения на размер позиции, чтобы не рисовать нереалистичные объёмы
    MAX_SHARES_PER_TRADE: 200,
    MAX_CUMULATIVE_SHARES_PER_MARKET: 500,
    MAX_NOTIONAL_FRACTION_OF_BANKROLL: 0.05,

    // Оценка газа на Polygon за merge complete set -> USDC (консервативно, реально дешевле)
    GAS_ESTIMATE_USD: 0.05,

    // https://docs.polymarket.com/trading/fees — taker fee = shares * rate * p * (1-p)
    TAKER_FEE_RATE_BY_CATEGORY: {
        crypto: 0.07,
        sports: 0.03,
        finance: 0.04,
        politics: 0.04,
        mentions: 0.04,
        tech: 0.04,
        economics: 0.05,
        culture: 0.05,
        weather: 0.05,
        geopolitics: 0.0,
        other: 0.05,
    },
    DEFAULT_TAKER_FEE_RATE: 0.05,
};
