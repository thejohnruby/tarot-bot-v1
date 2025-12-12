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

# ====== ТВОЙ ТЕЛЕГРАМ ТОКЕН ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
# ====== ТВой OPENAI API KEY ======
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

BASE_URL = os.getenv("BASE_URL")

# Админ
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# Храним timestamp, когда пользователь снова может получить карту
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
    keyboard = [[InlineKeyboardButton(
        "Получить карту дня", callback_data="daily_card")]]

    welcome = (
        "✨ Добро пожаловать в *Таро Онлайн*!\n\n"
        "Жми кнопку, чтобы получить карту дня.\n"
        "Карту можно получить только раз в сутки.\n"
        "Я напомню, когда появится новая."
    )

    await update.message.reply_text(
        welcome, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def daily_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    now = datetime.utcnow()

    # Админ всегда может
    if user_id == ADMIN_ID:
        await query.answer("Тяну карту, хозяин...")
        card = await generate_tarot_card()
        await query.edit_message_text(
            f"✨ Админская карта:\n\n{card}", parse_mode="Markdown"
        )
        return

    # Если пользователь уже получил карту сегодня
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

    # Отсечка 24 часа
    next_time = now + timedelta(days=1)
    next_allowed[user_id] = next_time

    # Создаем задачу уведомления ровно через сутки
    context.job_queue.run_once(
        notify_user,
        when=timedelta(days=1),
        chat_id=user_id,
        name=f"notify_{user_id}"
    )


async def notify_user(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.chat_id

    keyboard = [[InlineKeyboardButton(
        "Получить карту дня", callback_data="daily_card")]]

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="✨ Время новой карты дня!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        pass  # Если юзер удалил бота — ну и ладно

# -------------------------------------------------------
# webhook сервер
# -------------------------------------------------------


async def webhook_handler(request):
    data = await request.json()
    await request.app["bot"].process_update(Update.de_json(data, request.app["bot"].bot))
    return web.Response(text="OK")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # HANDLERS
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(daily_card, pattern="daily_card")
                    )

# aiohttp веб-сервер
    app = web.Application()
    app["bot"] = application

    app.add_routes([web.post("/webhook", webhook_handler)])

    # Чистим старые вебхуки
    await application.bot.delete_webhook()

    # Ставим новый
    await application.bot.set_webhook(f"{BASE_URL}/webhook")

    # Запуск job_queue + webhook-сервера
    await application.initialize()
    await application.start()

    port = int(os.getenv("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    print(f"Webhook запущен на порту {port}")

    await application.updater.start_polling()  # hack to keep job_queue alive
    await application.updater.idle()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
