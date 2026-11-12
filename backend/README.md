# Бэкенд «Каспийского диспетчера»

FastAPI, один процесс. Контракт — раздел 5 `CLAUDE.md`. **Сейчас все эндпоинты отдают моки** из `data/mock/*.json`; логика (граф, модель, диспетчер) появится позже без изменения контракта.

## Запуск одной командой

Нужен Python 3.11+.

```powershell
.\run.ps1          # Windows
```
```bash
./run.sh           # macOS / Linux / Git Bash
```

Скрипт сам создаст `.venv`, поставит зависимости, скопирует `.env.example` → `.env` и поднимет сервер на `0.0.0.0:8000` с автоперезагрузкой.

Проверка: `curl -H "X-API-Key: caspian-dev-key" http://localhost:8000/api/stats`

## Для фронтенда и Flutter

- **Базовый адрес:** `http://<ip-ноутбука>:8000/api` (локально `http://localhost:8000/api`). Телефон должен быть в той же сети; IP — `ipconfig` / `ifconfig`. Эмулятор Android ходит на `http://10.0.2.2:8000/api`.
- **Ключ:** заголовок `X-API-Key: <API_KEY из backend/.env>` на **каждом** запросе к `/api/*`. По умолчанию `caspian-dev-key`. Без ключа — `401 {"error": {"code": "unauthorized", ...}}`.
- **WebSocket:** `ws://<host>:8000/ws?api_key=<ключ>` (браузер не умеет слать заголовки в WS). Сообщения `{type, payload}`: `shipment.updated`, `alert.created`, `alert.updated`, `ledger.appended`, `stats.updated`, `weather.updated`. Не успеваете с WS — опрашивайте `/shipments`, `/alerts`, `/stats` раз в 3 с.
- **Документация и «попробовать»:** http://localhost:8000/docs (Swagger, кнопка **Authorize** → ключ), схема — `/openapi.json`.
- **Время** в JSON — UTC (`2026-11-12T11:00:00Z`). Показывать в `Europe/Moscow`: «сейчас» в демо — 12 ноя, 14:00.
- **Ошибки** всегда `{"error": {"code": "...", "message": "..."}}`.

### Фазы демо на моках

Сервер помнит одну «фазу» и отдаёт по ней грузы, алерты, счётчики, реестр, рейсы и погоду:

| Чтобы увидеть | Запрос | Что поменяется |
|---|---|---|
| Исходное состояние | `POST /api/demo/reset` | №01–03 «В пути», риск 7/6/5%, алертов нет, счётчики 0 |
| Съёмку инвойса №05 | `POST /api/documents` (multipart `shipment_id=sh-05`, `file`) → `POST /api/documents/doc-05/confirm` | черновик с полями (фарси → русский), затем пропуск `pass-05` и блок №4 в реестре |
| Шторм | `POST /api/scenarios` `{"preset": "storm_north"}` | №01–03 «Под риском» 82/74/68%, морской этап `blocked`, ETA +48 ч, алерт `alert-001` со статусом `new` |
| Принятие | `POST /api/alerts/alert-001/accept` `{"via": "web"}` (или `"telegram"`) | маршрут через Махачкалу, «Перестроен», новые пропуска `pass-0N-r1`, старые `reissued`, 3 блока `reissued`, счётчики 126 груз-ч / 596 640 ₽ / 1 824 кг CO₂. Повторный вызов → `already_accepted: true` |
| Отклонение | `POST /api/alerts/alert-001/reject` | алерт `rejected` |
| Подделку реестра | `POST /api/ledger/tamper` `{"index": 1}` → `GET /api/ledger/verify` | `valid: false, broken_at: 1`; пропуск с этим блоком в `/passes/verify` → `valid: false` |

Пример (PowerShell — `curl.exe`, не `curl`):

```bash
curl -X POST -H "X-API-Key: caspian-dev-key" -H "Content-Type: application/json" -d '{"preset":"storm_north"}' http://localhost:8000/api/scenarios
```

### Файлы моков

`data/mock/` можно читать напрямую, пока сервер не нужен: `<имя>.json` — исходная фаза, `<имя>.storm.json` — после шторма, `<имя>.accepted.json` — после принятия. `accept.json` — полный ответ на «Принять». ID грузов `sh-01` … `sh-05`.

Ограничения моков: `storm_full` и `congestion_astrakhan` → `501 not_in_mock`; `POST /shipments` и `/reroute` отвечают, но ничего не сохраняют; ответа `409 superseded` на моках нет; порядок фиксирован (инвойс №05 → шторм → принятие), поэтому после принятия пропуск №05 считается выпущенным.

`delta` в `/alternatives` — к плановому маршруту: `hours` — задержка прибытия к плану по прогнозу, `rub` — доплата за перевозку, `co2_kg` — разница CO₂.

## Как устроено

```
app/main.py       роуты, X-API-Key, CORS, ошибки, /ws
app/models.py     Pydantic-модели (раздел 4) + запросы/ответы (раздел 5)
app/state.py      мок-состояние: фазы и выбор файла
app/ledger.py     hash-chain (уже настоящий: хэш, добавление, проверка)
app/documents.py  хэш документа; распознавание — TODO
app/graph.py predictor.py dispatcher.py weather.py bot/   — TODO
data/seed.json    узлы, рёбра, рейсы, грузы, документы, пропуска, реестр
scripts/gen_mocks.py  строит seed.json и все моки по формулам DEMO_SCENARIO
```

**Моки руками не правим.** Поменяли расстояние, тариф или рейс в `scripts/gen_mocks.py` — запустили:

```bash
.venv/Scripts/python scripts/gen_mocks.py
```

Скрипт печатает сверку с числами сценария (298 320 ₽, 596 640 ₽, 126 груз-ч, −6,7% для №01, −6,9% для трёх грузов…) и падает, если что-то разошлось. Каждый мок проверяется Pydantic-моделями контракта.
