require('dotenv').config({ path: require('path').join(__dirname, '.env') });
const { Telegraf } = require('telegraf');
const { askDeepSeek } = require('./deepseek');
const { getUser, upsertUser, incrementFreeUsed, setSubscribed, isSubscribed } = require('./db');

const {
    TELEGRAM_BOT_TOKEN,
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL = 'https://api.deepseek.com',
    BOT_PERSONA = 'Ты дружелюбный и точный ассистент.',
    FREE_MESSAGES = '10',
} = process.env;

if (!TELEGRAM_BOT_TOKEN) {
    console.error('TELEGRAM_BOT_TOKEN не задан в .env — см. .env.example. Получи токен у @BotFather.');
    process.exit(1);
}
if (!DEEPSEEK_API_KEY) {
    console.error('DEEPSEEK_API_KEY не задан в .env — см. .env.example.');
    process.exit(1);
}

const FREE_LIMIT = parseInt(FREE_MESSAGES, 10);
const bot = new Telegraf(TELEGRAM_BOT_TOKEN);

// Короткая история диалога в памяти, на процесс. Для продакшена стоит вынести в БД.
const history = new Map();
function pushHistory(id, role, content) {
    const h = history.get(id) || [];
    h.push({ role, content });
    while (h.length > 12) h.shift();
    history.set(id, h);
    return h;
}

bot.start(async (ctx) => {
    await upsertUser(ctx.from.id, ctx.from.username || '');
    await ctx.reply(
        `Привет! Я AI-ассистент на DeepSeek.\n` +
        `Первые ${FREE_LIMIT} сообщений — бесплатно, дальше — подписка (/buy).\n` +
        `Просто пиши вопрос.`
    );
});

bot.command('buy', async (ctx) => {
    await ctx.replyWithInvoice({
        title: 'Подписка на 30 дней',
        description: 'Безлимитный доступ к AI-ассистенту на 30 дней',
        payload: `sub_30d_${ctx.from.id}`,
        provider_token: '', // Telegram Stars — provider_token пустой
        currency: 'XTR',
        prices: [{ label: 'Подписка 30 дней', amount: 100 }], // 100 Stars
    });
});

bot.on('pre_checkout_query', async (ctx) => {
    await ctx.answerPreCheckoutQuery(true);
});

bot.on('successful_payment', async (ctx) => {
    const until = new Date();
    until.setDate(until.getDate() + 30);
    await setSubscribed(ctx.from.id, until);
    await ctx.reply(`Оплата получена. Подписка активна до ${until.toISOString().slice(0, 10)}. Спасибо!`);
});

bot.on('text', async (ctx) => {
    if (ctx.message.text.startsWith('/')) return;

    await upsertUser(ctx.from.id, ctx.from.username || '');
    const user = await getUser(ctx.from.id);

    if (!isSubscribed(user) && (user?.free_used || 0) >= FREE_LIMIT) {
        return ctx.reply(`Бесплатный лимит (${FREE_LIMIT} сообщений) исчерпан. Оформи подписку: /buy`);
    }

    const h = pushHistory(ctx.from.id, 'user', ctx.message.text);
    await ctx.sendChatAction('typing');

    try {
        const answer = await askDeepSeek({
            baseUrl: DEEPSEEK_BASE_URL,
            apiKey: DEEPSEEK_API_KEY,
            persona: BOT_PERSONA,
            history: h,
        });
        pushHistory(ctx.from.id, 'assistant', answer);
        if (!isSubscribed(user)) await incrementFreeUsed(ctx.from.id);
        await ctx.reply(answer);
    } catch (err) {
        console.error(err);
        await ctx.reply('Что-то пошло не так с AI-провайдером, попробуй ещё раз чуть позже.');
    }
});

bot.launch();
console.log('Telegram bot started (polling).');

process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
