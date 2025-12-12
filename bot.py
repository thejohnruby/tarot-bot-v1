import os
from datetime import datetime, timedelta
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from openai import AsyncOpenAI

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("BASE_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

next_allowed = {}


async def generate_tarot_card():
    prompt = """
Ты — профессиональный таролог с глубоким опытом. 
Случайным образом вытяни одну карту из классической колоды Таро.

Дай ответ строго в таком формате:

Название карты (на русском)

Короткое значение карты

Совет карты на сегодняшний день

Пиши дружелюбно, понятно, немного мистически, чтобы вызвать интерес и в то же время красиво, с разелением на обзацы. 
Каждый абзац с новой строки с красивым символом. 
Объём до 150 слов. 
"""
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Получить карту дня", callback_data="daily_card")]]
    welcome = (
        "✨ Добро пожаловать!\n\n"
        "Жми кнопку, чтобы получить карту дня.\n"
        "Одна карта в сутки. Я напомню, когда можно снова."
    )
    await update.message.reply_text(
        welcome, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def daily_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    now = datetime.utcnow()

    if user_id == ADMIN_ID:
        await query.answer("Тяну карту...")
        card = await generate_tarot_card()
        await query.edit_message_text(
            f"✨ Админская карта:\n\n{card}", parse_mode="Markdown"
        )
        return

    if user_id in next_allowed and now < next_allowed[user_id]:
        reset_time = next_allowed[user_id].strftime("%H:%M UTC")
        await query.answer(
            f"Ты уже получал карту. Следующая будет доступна после {reset_time}.",
            show_alert=True
        )
        return

    await query.answer("Тяну карту...")

    card = await generate_tarot_card()
    await query.edit_message_text(
        f"✨ *Твоя карта дня:*\n\n{card}", parse_mode="Markdown"
    )

    next_time = now + timedelta(days=1)
    next_allowed[user_id] = next_time

    # напоминание через сутки
    context.job_queue.run_once(
        notify_user,
        when=timedelta(days=1),
        chat_id=user_id,
        name=f"notify_{user_id}"
    )


async def notify_user(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.chat_id
    keyboard = [[InlineKeyboardButton("Получить карту дня", callback_data="daily_card")]]

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="✨ Время новой карты дня!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        pass


# ---------------------------
# Webhook обработчик
# ---------------------------

async def webhook_handler(request):
    bot_app = request.app["application"]
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return web.Response(text="OK")


# ---------------------------
# Главный запуск
# ---------------------------

async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(daily_card, pattern="daily_card"))

    # Ставим webhook
    await application.bot.delete_webhook()
    await application.bot.set_webhook(f"{BASE_URL}/webhook")

    # Инициализация job_queue и обработчиков
    await application.initialize()
    await application.start()

    # aiohttp сервер
    aio_app = web.Application()
    aio_app["application"] = application
    aio_app.router.add_post("/webhook", webhook_handler)

    port = int(os.getenv("PORT", 10000))
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    print(f"Webhook слушает порт {port}")
    # держим процесс живым
    await application.wait_for_stop()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
