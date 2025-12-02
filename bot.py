import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)
from openai import AsyncOpenAI

# Загружаем .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Хранение: когда пользователь может снова получить карту
next_allowed = {}

# Хранение: назначены ли пользователю уведомления
pending_notifications = {}


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

    keyboard = [
        [InlineKeyboardButton("Получить карту дня",
                              callback_data="daily_card")]
    ]

    text = (
        "✨ Добро пожаловать в *Таро Онлайн*!\n\n"
        "Нажми кнопку ниже, чтобы получить свою карту дня.\n"
        "Доступна один раз в сутки."
    )

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def daily_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    now = datetime.utcnow()

    # ==== АДМИН: без лимитов ====
    if user_id == ADMIN_ID:
        await query.answer("Админский доступ. Тяну карту...")
        tarot_text = await generate_tarot_card()
        await query.edit_message_text(
            f"✨ *Админская карта:*\n\n{tarot_text}",
            parse_mode="Markdown"
        )
        return

    # ==== Обычные пользователи ====
    if user_id in next_allowed and now < next_allowed[user_id]:
        reset_time = next_allowed[user_id].strftime("%H:%M UTC")
        await query.answer(
            f"Карта уже получена. Следующая будет доступна после {reset_time}.",
            show_alert=True
        )
        return

    # ==== Тянем карту ====
    await update.callback_query.answer("Тяну карту...")

    tarot_text = await generate_tarot_card()

    await update.callback_query.edit_message_text(
        f"✨ *Твоя карта дня:*\n\n{tarot_text}",
        parse_mode="Markdown"
    )

    # Назначаем следующий доступ через 24 часа
    next_time = now + timedelta(days=1)
    next_allowed[user_id] = next_time

    # Запоминаем, что нужно уведомить
    pending_notifications[user_id] = next_time


# Повторяющаяся задача — проверка, кому пора прислать уведомление
async def notification_worker(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.utcnow()
    to_notify = []

    for user_id, notify_time in list(pending_notifications.items()):
        if now >= notify_time:
            to_notify.append(user_id)

    for user_id in to_notify:
        keyboard = [[InlineKeyboardButton(
            "Получить карту дня", callback_data="daily_card")]]
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="✨ Новая карта дня доступна!",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            pass  # Человек может быть заблокировал бота

        del pending_notifications[user_id]


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(daily_card, pattern="daily_card"))

    app.run_polling()


if __name__ == "__main__":
    main()
