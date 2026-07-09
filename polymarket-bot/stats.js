const { db } = require('./db');

db.get(`SELECT COUNT(*) as trades, COALESCE(SUM(net_profit),0) as profit FROM trades`, [], (err, row) => {
    if (err) throw err;
    db.get(`SELECT bankroll, timestamp FROM snapshots ORDER BY id DESC LIMIT 1`, [], (err2, snap) => {
        if (err2) throw err2;
        console.log(`Trades: ${row.trades}`);
        console.log(`Total net profit (virtual): $${row.profit.toFixed(4)}`);
        console.log(`Current bankroll: $${snap ? snap.bankroll.toFixed(2) : 'n/a'}`);
        console.log(`Last snapshot: ${snap ? snap.timestamp : 'n/a'}`);
        db.all(`SELECT timestamp, question, shares, cost, net_profit FROM trades ORDER BY id DESC LIMIT 10`, [], (err3, rows) => {
            if (err3) throw err3;
            console.log('\nLast trades:');
            for (const t of rows) {
                console.log(`  ${t.timestamp} | ${t.question?.slice(0, 50)} | shares=${t.shares?.toFixed(2)} cost=$${t.cost?.toFixed(2)} profit=$${t.net_profit?.toFixed(4)}`);
            }
            process.exit(0);
        });
    });
});
