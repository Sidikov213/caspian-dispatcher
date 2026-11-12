# Hackathon Bot Starter (aiogram 3 + LLM)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # вписать BOT_TOKEN и LLM_API_KEY
python -m app.main
```

**Что уже есть:** меню, диалог с ИИ с памятью (/reset), «заявка свободным текстом → ИИ раскладывает в JSON → бэкенд», «мои заявки», админские /stats и /broadcast.

**Под кейс меняется** блок `PROJECT_NAME / ABOUT_TEXT / ITEM_SCHEMA` в `app/handlers.py` и `SYSTEM_PROMPT` в `.env`.

**Бэкенд:** пока `BACKEND_URL` пуст, всё пишется в `local_db.json` — бот работает автономно. Когда фронтендер поднимет API, бот ходит в:
- `POST /api/users` `{telegram_id, name}`
- `GET /api/users` → `[{telegram_id, name}]`
- `POST /api/items` `{telegram_id, ...поля}` → `{id, status, ...}`
- `GET /api/items?telegram_id=` → `[...]`

Тот же API использует Flutter-приложение и сайт — одна база на всех.
