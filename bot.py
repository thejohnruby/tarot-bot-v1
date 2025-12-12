import os
import logging
from datetime import datetime, timedelta
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from openai import AsyncOpenAI
import asyncio

logging.basicConfig(level=logging.INFO)

# ====== ТЕЛЕГРАМ ТОКЕН ======
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ====== OPENAI KEY ======
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# BASE URL для webhook
BASE_URL = os.getenv("BASE_URL")

# ID админа
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# Ограничение на получение карты раз в сутки
next_allowed = {}


async def generate_tarot_card():
    prompt = """
Ты — профессиональный таролог с глубоким опытом. 
Случайным образом вытяни одну карту из классической колоды Таро Уэйта, 78 карт.

Дай ответ строго в таком формате:

Название карты (на русском)

Короткое значение карты

Совет карты на сегодняшний день

Пиши дружелюбно, понятно и немного мистически, чтобы вызвать интерес. В то же время красиво, с разделением на обзацы. 
Каждый абзац с новой строки с красивым символом. 
Объём до 220 слов. 
"""
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Получить карту дня", callback_data="daily_card")]]

    text = (
        "✨ Добро пожаловать в *Таро Онлайн*!\n\n"
        "Жми кнопку, чтобы получить карту дня.\n"
        "Карту можно получить только раз в сутки.\n"
        "Я напомню, когда появится новая."
    )

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def daily_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    now = datetime.utcnow()

    # Админ всегда может тянуть
    if user_id == ADMIN_ID:
        await query.answer("Тяну карту, хозяин...")
        card = await generate_tarot_card()
        await query.edit_message_text(f"✨ Админская карта:\n\n{card}", parse_mode="Markdown")
        return

    # Если рано
    if user_id in next_allowed and now < next_allowed[user_id]:
        reset_time = next_allowed[user_id].strftime("%H:%M UTC")
        await query.answer(f"Следующая карта будет доступна после {reset_time}.", show_alert=True)
        return

    await query.answer("Тяну карту...")

    card = await generate_tarot_card()
    await query.edit_message_text(f"✨ *Твоя карта дня:*\n\n{card}", parse_mode="Markdown")

    # 24 часа блокировки
    next_allowed[user_id] = now + timedelta(days=1)

    # Уведомление
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


# =================================================================
# WEBHOOK
# =================================================================

async def webhook_handler(request):
    application: Application = request.app["application"]
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return web.Response(text="OK")


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не найден.")
    if not BASE_URL:
        raise RuntimeError("BASE_URL не найден.")

    application = Application.builder().token(BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(daily_card, pattern="daily_card"))

    # Чистим webhook
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.initialize()
    await application.start()

    # Настраиваем новый webhook
    await application.bot.set_webhook(f"{BASE_URL}/webhook")

    # aiohttp сервер
    web_app = web.Application()
    web_app["application"] = application
    web_app.add_routes([web.post("/webhook", webhook_handler)])

    port = int(os.getenv("PORT", 10000))

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logging.info(f"Webhook запущен на порту {port}")

    # Держим процесс живым
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
