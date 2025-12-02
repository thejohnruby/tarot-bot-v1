
# Tarot Online Bot

Телеграм-бот, который выдаёт карту дня.
Пользователь — 1 карта в сутки.
Админ — без лимитов.

## Запуск локально

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

## Деплой на Render

1. Загрузить проект на GitHub
2. Создать новый Web Service
3. Команда запуска:

```
python bot.py
```

4. Добавить переменные окружения:

- BOT_TOKEN
- OPENAI_API_KEY
- ADMIN_ID
