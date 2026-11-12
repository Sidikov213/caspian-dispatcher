# CLAUDE.md — «Каспийский диспетчер»

Этот файл читают Claude Code и Cursor у всех участников. Он — единственный источник правды по архитектуре и контракту. Меняет его только тимлид; изменение контракта API = сообщение в общий чат.

Все числа, расписание и порядок демо — в `docs/DEMO_SCENARIO.md`. Сиды и моки обязаны воспроизводить его числа. Макеты — в `docs/design/`; в них остались старые иллюстративные числа, при расхождении прав сценарий.

## 1. Кейс

Финал международного хакатона IV Каспийского цифрового форума (Махачкала). Кейс 2 «Smart Caspian Transit», трек «Цифровая экосистема МТК "Север–Юг"».

Боль: рассинхронизация ж/д, авто и моря, простои на таможне, погода на Каспии срывает графики.

Требования MVP:
1. Предиктивная модель задержек (история + погода + загрузка портов), пример из кейса — стыковка ж/д состава и парома.
2. Pre-clearance: автоматическое таможенное оформление на распределённом реестре или защищённых API.
3. Единое окно логиста: цифровой двойник груза, CO₂ (ESG), альтернативные маршруты при форс-мажоре.

## 2. Концепция

**Одна фраза:** «Все показывают, где груз сейчас. Мы говорим, где он застрянет через двое суток, — и маршрут уже перестроен».

**Киллерфича — ИИ-диспетчер.** Система видит угрозы на 48 ч вперёд, находит грузы, у которых сорвётся стыковка с паромом, считает альтернативы по графу и расписанию рейсов и пишет логисту в Telegram готовое решение с цифрами (часы, ₽, CO₂) и ценой бездействия. Логист жмёт «Принять» → маршрут на сайте перестраивается, пропуск переоформляется на новый пункт, запись уходит в реестр.

**Главная мысль защиты:** возможная задержка отправления 18 ч оборачивается потерей 48 ч, потому что паром ходит раз в двое суток и стыковка срывается.

Решение всегда подтверждает человек. ИИ предлагает и исполняет после подтверждения.

**Клиенты, один бэкенд:**
- `website/` (Next.js 16, статический экспорт) — окно логиста: карта, двойники грузов, прогноз по этапам, альтернативы, счётчик, лента реестра.
- `mobile/` (Flutter) — экспедитор: фото документа → поля → QR-пропуск, статусы груза. Три экрана, не больше. Контракт и дизайн — `docs/FLUTTER_CONTRACT.md`.
- Telegram-бот — диспетчер: алерты с кнопками, вопросы свободным текстом.
- Telegram Mini App (`backend/app/miniapp/`, `/tg/`) — пульт логиста внутри Telegram: Обзор, Грузы с двойником и новым грузом, Решения с принятием.

**Продакшен:** `https://caspian-dispatcher.ru` (запасной адрес `https://129-101-122-103.sslip.io` работает так же) — сайт на `/`, API на `/api`, WebSocket на `/ws`, мини-приложение на `/tg/`. Один VPS, Caddy с HTTPS, выкатка через GitHub Actions (`backend/scripts/deploy.ps1`). Telegram-бот работает только там.

**Бонус:** фото инвойса на фарси → поля декларации на русском.

## 3. Архитектура

```
website (Next.js, SVG-схема)   mobile (Flutter)   Telegram: бот + Mini App
        │  REST + WS              │ REST            │
        └──────────────┬──────────┴─────────────────┘
                 backend (FastAPI, один процесс)
   ┌───────────┬───────────┬────────────┬───────────┬─────────┐
   graph.py   predictor.py dispatcher.py documents.py ledger.py bot/
   networkx   CatBoost     оркестратор   кэш-черновик hash-chain aiogram 3
   └───────────┴───────────┴────────────┴───────────┴─────────┘
        state: in-memory + data/seed.json     weather: Open-Meteo
```

Правила архитектуры:
- **Цифры считает код, а не LLM.** Задержку даёт модель, маршруты — граф, CO₂ и деньги — формулы. Фактически LLM используется только для свободных вопросов в боте через tools и только при заданном `LLM_API_KEY`. Текст алерта всегда из шаблона по готовым цифрам. Поля документа — закэшированный черновик демо-инвойса (vision-LLM запланирован, не подключён).
- **Без LLM всё работает:** бот отвечает на кнопки, алерт пишется шаблоном, документ — из кэша.
- **Граф — networkx**, не Neo4j. В питче: «в продакшене — графовая БД».
- **Реестр — hash-chain** (каждый блок хранит хэш предыдущего) + эндпоинт проверки целостности. Блокчейном его не называем. Реестр у одного оператора показывает сторонние изменения; от самого оператора защищают копии у участников. В прототипе копия одна: пропуск на телефоне экспедитора. В продакшене — узлы у таможен и портов.
- **QR-пропуск — подписанный JWT (HS256)**, внутри `doc_hash` и `block_hash`. Действителен, если подпись верна, статус `active`, запись о выдаче цела и хэш документов совпадает. Это внутренний пропуск сервиса, интеграции с портом нет.
- **Погода:** Open-Meteo Marine (Каспий отдаёт, проверено), `forecast_days=7`, обновление раз в 30 мин, кэш в файл. Алерты строятся по ближайшим 48 ч. Кнопка сценария умножает реальный прогноз, а не выдумывает погоду.
- **Два шага прогноза:** классификатор CatBoost даёт вероятность срыва стыковки; самое раннее возможное отправление и факторы в часах считает код по прогнозу погоды; обычный код по расписанию рейсов находит первый подходящий рейс и считает задержку прибытия. `PREDICTOR=catboost|formula` в `.env`; нет модели или catboost — откат на формулу с записью в лог. Модель обучена на синтетической истории (`scripts/gen_history.py`, `scripts/train.py`), так и говорим.
- Бот живёт в процессе бэкенда (polling как asyncio-задача) и вызывает функции напрямую.
- Пуши в приложение (FCM) — подписчик той же шины `events`, рядом с уведомителем бота (`app/push.py`): `alert.created` и принятие решения → пуш на все устройства из `POST /api/devices`. Без `firebase-admin` (тяжёлая зависимость): FCM HTTP v1, JWT сервисного аккаунта подписывается PyJWT + `cryptography`. Ключ — JSON в `FIREBASE_CREDENTIALS` (на сервере `secrets/firebase-admin.json` из секрета GitHub `FIREBASE_ADMIN_JSON`); без него пуши выключены.
- Состояние в памяти, сид из `data/seed.json`, `POST /api/demo/reset` возвращает всё к началу демо (в том числе удаляет созданные вручную грузы).
- В файлах, переживают reset и перезапуск: аккаунты сайта `data/accounts.json`, привязки Telegram `data/users.json`, кэш погоды `data/weather_cache.json`, FCM-токены устройств `data/devices.json`. Все не в git.

Наблюдатель угроз (`dispatcher.watch`) запускается при старте и reset, после каждого обновления прогноза и после запуска сценария. Угроза — (вид, порт, рейс): у запланированного рейса в ближайшие 48 ч в момент отправления волна в порту не ниже предела (или порт под затором сценария). По каждой новой угрозе — алерт через конвейер ниже. Одна угроза — один активный алерт, и груз входит только в один активный (`new`) алерт: новая угроза по тем же грузам закрывает прежний алерт (`superseded`, `status_note` «заменён алертом …»); прогноз изменился существенно (окно сдвинулось на 3 ч и больше или пик волны на 0,5 м) — старый алерт `superseded`, создаётся новый; угроза ушла до решения — алерт `superseded` с пометкой «угроза снята». Сценарий — не отдельная ветка: он только подменяет прогноз (шторм, затор) и зовёт наблюдателя. Источник угрозы в алерте: `source: forecast | scenario`.

Конвейер диспетчера (`dispatcher.build_alert`), запускается наблюдателем по угрозе:
1. `affected` = грузы, чья стыковка — рейс угрозы
2. для каждого: `predictor.predict(...)` → вероятность срыва стыковки, самое раннее отправление, факторы
3. «ничего не делать» = первый рейс из расписания после самого раннего отправления → задержка прибытия
4. `graph.alternatives(...)` → до 3 маршрутов; для каждого проверки: волна в порту в момент отправления ниже предела, рейс есть, свободного места хватает, груз успевает к окончанию приёма, тип груза допустим
5. выбрать лучший, посчитать расчётную экономию против «ничего не делать» (формулы в DEMO_SCENARIO.md)
6. создать Alert, текст по шаблону, отправить в Telegram и в WS; если допустимого маршрута нет — алерт без предложения
7. accept, одна операция под `asyncio.Lock`: проверить, что алерт `new` (иначе вернуть «уже принято») → проверить, что `from_route` каждого груза — его текущий маршрут (иначе 409 `superseded`, пересчёт) → заново проверить и зарезервировать место на рейсе (нет места → алерт `superseded`, пересчёт) → сменить маршрут → выпустить новый пропуск → отозвать старый → блок в реестр → запись Decision → обновить stats → открытые алерты с теми же грузами `superseded` с пометкой «по этим грузам решение уже принято»
8. если выпуск пропуска не удался: груз получает `pass_state: reissue_pending`, старый пропуск остаётся активным, есть повтор; экономия начисляется один раз

Tools LLM-агента в боте: `get_shipments(tg_id)`, `get_shipment(id)`, `get_alternatives(id)`, `get_weather()`, `explain_risk(id)`. Менять состояние агент не может, только кнопки.

## 4. Модель данных

```
Node      {id, name, country, type: port|station|border|city, lat, lon, congestion: 0..1,
           facts?: [string], sources?: [url]}   # проверенные факты о порте и ссылки (Махачкала, Астрахань)
Edge      {id, from, to, mode: rail|sea|road, branch: west|transcaspian|east,
           distance_km, base_hours, cost_rub_per_t, co2_g_per_tkm,
           path?: [[lat, lon]]}   # промежуточные точки для карты (без узлов): море по акватории,
                                  # суша вдоль трасс; только рисование, в расчётах не участвует
Shipment  {id, title, cargo_type, weight_t, owner_tg_id, origin, destination,
           stage: planned|in_transit|delivered,
           risk_level: low|medium|high, rerouted: bool,
           display_status: planned|in_transit|at_risk|rerouted|delivered,
           position: {lat, lon}, current_leg, route: Route,
           planned_eta, eta, risk: Risk, pass_id,
           pass_state: none|active|reissue_pending,
           manual?: bool}    # создан вручную (POST /shipments); при reset исчезает
           # display_status считает бэкенд: delivered → at_risk (risk_level=high)
           # → rerouted → in_transit → planned. Клиенты сами его не выводят.
Sailing   {id, from, to, departure, cutoff, duration_h, capacity_t, booked_t,
           status: scheduled|cancelled|departed, cancel_reason}
Decision  {id, alert_id, ts, accepted_via: web|telegram, accepted_by?: {name, role}, items: [{shipment_id,
           saved_hours, saved_rub, co2_delta_kg, sailing_id}]}
           # счётчики stats = сумма записей Decision, числа в записи заморожены
Route     {id, legs: [Leg], total_hours, total_cost_rub, total_co2_kg, branch}
Leg       {index, edge_id, from, to, mode, sailing_id, planned_start, planned_end,
           predicted_delay_h, status: done|active|pending|blocked}
Risk      {miss_probability: 0..1, level: low|medium|high,
           departure_shift_h,   # на сколько позже планового рейса возможно отправление
           arrival_delay_h,     # задержка прибытия, если рейс отменят
           factors: [{name, label, impact_hours}],   # часы — расчёт по прогнозу и расписанию
           probability_drivers?: [{name, label, impact_pp}]}
           # необязательно: три главных признака по SHAP классификатора CatBoost, вклад в
           # вероятность срыва в п. п.; у формулы и сухопутных маршрутов — null
Scenario  {id, type: ice|storm|congestion|customs, hazard?: ice|storm|congestion|customs, note?,
           title, blocked_edges: [id],
           affected_nodes: [id], start, end, starts_in_h, params: {wave_height_m, wind_ms},
           zone?: [[lat, lon]]}   # полигон зоны угрозы для карты; клиенты его не угадывают
           # starts_in_h — через сколько часов от sim_now начинается угроза (storm_north — 36)
Alert     {id, scenario_id, created_at, starts_in_h, severity, title, text,
           items: [{shipment_id, action: reroute|wait, from_route, to_route,
                    sailing_id, delay_vs_plan_h, saved_hours, saved_rub, co2_delta_kg}],
           totals: {saved_hours, saved_rub, co2_delta_kg, co2_delta_pct},
           do_nothing: {delay_hours, loss_rub},
           port_load: {node_id, before, after},
           options: [{id, title, route: Route|null, delay_vs_plan_h, saved_hours,
                      saved_rub, co2_delta_kg, recommended}],
           status: new|accepted|rejected|superseded, accepted_at, accepted_via,
           accepted_by?: {name, role: logist|expeditor},   # кто принял: Bearer входа сайта, мини-приложение, бот
           source?: forecast|scenario,   # откуда угроза: наблюдатель нашёл в прогнозе или сценарий
           hazard?: ice|storm|congestion|customs,   # тип угрозы; тексты по нему — app/hazards.py
           card?: {kind, headline, subtitle, period, metrics: [{key, label, value}],
                   route: {sailing_label, from, to, departure} | null,
                   impact: {shipments, weight_t, max_risk_pct}, note,
                   decision: null | {status: accepted|rejected, title, detail, via, via_label, accepted_by_name}},
           # card — компактная карточка из тех же данных, что text/items/options/accepted_*; готовые
           # строки по разделу 9, клиент рисует как есть. text не меняется. note у шторма — «Стресс-тест: …»
           status_note?}                 # почему закрыт: «угроза снята», «прогноз изменился…»
           # все деньги и часы до наступления события — расчётные
           # options — до трёх вариантов решения, рекомендованный первый; числа — сумма по грузам
           # алерта. id: тег маршрута (mkh, west…), best — лучший обход для каждого груза,
           # wait — «ждать следующий рейс», он равен «Отклонить» (/reject). items и totals
           # описывают рекомендованный вариант, после принятия — принятый.
Document  {id, shipment_id, type: invoice|cmr|packing_list, source_lang,
           image_url, fields: {seller, buyer, goods, hs_code, weight_kg,
           value, currency, origin_country}, checks: [{name, ok, note}],
           status: draft|confirmed, hash}
Pass      {id, shipment_id, checkpoint_node, token (JWT), doc_hash, block_hash,
           valid_until, status: active|reissued|revoked}
Block     {index, ts, event: issued|reissued|verified, shipment_id,
           checkpoint_node, doc_hash, prev_hash, hash}
```

## 5. Контракт API

База: `/api` (продакшен `https://caspian-dispatcher.ru/api`). JSON, UTF-8, время в ISO 8601 UTC. Авторизация на всех `/api/*`: заголовок `X-API-Key` (сайт, приложение, бот) **или** `Authorization: Bearer <сессия мини-приложения>` из `POST /api/tg/auth`. Токен входа сайта (`/api/auth/*`) доступа к API не даёт, но если пришёл вместе с `X-API-Key`, сервер проверяет права роли (см. «Аккаунты»). Ошибки: `{"error": {"code": "...", "message": "...", "fields"?: [string]}}`; `fields` — поля запроса с ошибкой, где это известно. Неверное тело запроса — 422.

| Метод | Путь | Запрос | Ответ |
|---|---|---|---|
| GET | `/graph` | — | `{nodes: [Node], edges: [Edge]}` |
| GET | `/shipments?owner_tg_id=` | — | `[Shipment]` |
| GET | `/shipments/{id}` | — | `Shipment` |
| POST | `/shipments` | `{title, cargo_type, weight_t, origin, destination}` | `Shipment`; 422: `title` 1–120 символов, `cargo_type` из `grain\|metal\|equipment\|textile\|fertilizer\|explosives`, `0 < weight_t ≤ 5000`, `origin` и `destination` — узлы графа и не совпадают (`node_not_found`, `validation_error`), нет маршрута — `no_route` |
| GET | `/shipments/{id}/alternatives` | — | `[{route: Route, risk: Risk, delta: {hours, rub, co2_kg}, recommended: bool}]` |
| POST | `/shipments/{id}/reroute` | `{route_id}` | `Shipment` |
| GET | `/weather` | — | `{updated_at, stale: bool, source: "open-meteo" \| "cache", points: [{node_id, wave_height_m, wind_ms, forecast: [{ts, wave_height_m}]}]}` |
| GET | `/scenarios/presets` | — | `[{key, title, hazard, main, note}]`; `main: true` — главный сценарий (`ice_north`), у шторма `note` «Стресс-тест: …» |
| GET | `/scenarios` | — | `[Scenario]` — активные сценарии (после reset пусто), только чтение; нужен клиентам для `Scenario.zone` после перезагрузки страницы |
| POST | `/scenarios` | `{preset: "ice_north" \| "storm_north" \| "storm_full" \| "congestion_astrakhan"}` | `{scenario: Scenario, alert: Alert}`; главный — `ice_north` (лёд), шторм — стресс-тест |
| GET | `/alerts?status=` | — | `[Alert]` |
| POST | `/alerts/{id}/accept` | `{via: "web" \| "telegram", option_id?: string}` | `{alert: Alert, shipments: [Shipment], blocks: [Block], decision: Decision}`; без `option_id` — рекомендованный вариант; повтор → 200 с тем же результатом и `already_accepted: true`; устарел → 409 `superseded`; нет варианта → 404 `option_not_found`; `option_id: "wait"` → 422 `use_reject` |
| GET | `/sailings?from=&to=` | — | `[Sailing]` |
| POST | `/shipments/{id}/pass/retry` | — | `{shipment: Shipment, pass: Pass}` |
| POST | `/alerts/{id}/reject` | — | `Alert` |
| POST | `/documents` | multipart: `shipment_id`, `file` | `Document` (status draft) |
| POST | `/documents/{id}/confirm` | `{fields}` (с правками) | `{document: Document, pass: Pass, block: Block}`; 422 `document_invalid`, `error.fields` — список полей: обязательные `goods, hs_code, weight_kg, value, origin_country` не пустые, `weight_kg > 0` и в пределах 5% от заявки, `value > 0`, `currency` из `USD, EUR, RUB, CNY, IRR, AZN, KZT, TMT, INR, AED, TRY`, `hs_code` — 6–10 цифр (пробелы и точки допустимы) |
| GET | `/passes?shipment_id=` | — | `[Pass]` — все пропуска, включая переоформленные, новые сверху |
| GET | `/passes/{id}` | — | `Pass` |
| POST | `/passes/verify` | `{token}` | `{valid: bool, shipment_id, checkpoint_node, reason}` |
| GET | `/ledger` | — | `[Block]` |
| GET | `/ledger/verify` | — | `{valid: bool, broken_at: int \| null}` |
| POST | `/ledger/tamper` | `{index}` (только демо) | `{ok: true}` |
| GET | `/stats` | — | `{saved_hours, saved_rub, co2_saved_kg, co2_saved_pct, decisions, shipments_total, at_risk}` (сумма по Decision; часы — груз-часы; `co2_saved_pct` — на сколько % ниже CO₂ по принятым решениям к исходным маршрутам этих грузов, 6.9 → «−6,9% CO₂», клиенты сами не считают) |
| POST | `/devices` | `{token, platform: "ios" \| "android"}` + `Authorization: Bearer <токен /auth/login>` | `{ok: true, push_enabled: bool}`; без Bearer — 401 `invalid_token`; токен с другого аккаунта переезжает к этому; `push_enabled: false` — на сервере нет ключа Firebase |
| DELETE | `/devices` | `{token}` + Bearer | `{ok: true, push_enabled}` (выход из приложения; неизвестный токен — тоже ok) |
| POST | `/users/link` | `{telegram_id, name}` | `{ok: true}` |
| POST | `/auth/register` | `{name, email, password, role: "logist" \| "expeditor"}` | `{token, user: {id, name, email, role}}`; 409 `email_taken`; 422 `weak_password` (< 6 символов), `invalid_email` |
| POST | `/auth/login` | `{email, password}` | `{token, user}`; 401 `invalid_credentials` |
| GET | `/auth/me` | заголовок `Authorization: Bearer <token>` | `user` (с `permissions`); 401 `invalid_token` |
| POST | `/demo/reset` | — | `{ok: true}` |
| GET | `/demo/check` (только демо) | — | `{ok, sim_now, weather: {source, stale, updated_at}, checks: [{name, label, expected, actual, ok}], problems: [string]}`: проверка `forecast_quiet` — создал ли наблюдатель алерт на текущей погоде до сценария (не ошибка, `ok: true`, но в `actual` прямо: порт, волна, рейс); проверка «начальное состояние спокойное» (до сценария ни один груз не «Под риском», при провале — причина: груз, риск, волна в порту) и storm_north на копии исходного состояния, сверка с эталоном (риски 82/74/68% ±5 п. п. и порядок №01 > №02 > №03; точно: +18 ч, +48 ч, +6 ч, 126 груз-ч, 596 640 ₽, рекомендован `mkh`); `problems` — почему разошлось. Состояние не меняет |
| GET | `/data-sources` | — | `{sources: [{id, title, provides, type: "real" \| "modeled" \| "synthetic", url, urls?, updated_at, note}], corridor_facts: [{text, source}], backtest: {...} \| null}` — откуда данные и насколько они настоящие; `backtest` — сводка ретроспективной симуляции на исторической погоде (`data/backtest.json`, `scripts/backtest.py`), `backtest.chart` — путь к графику на сайте |
| GET | `/model` | — | `{summary, active: "catboost" \| "formula", requested, fallback_reason, synthetic: true, note, used_at_runtime: {miss_probability, departure_shift_and_delays, shift_regressor}, trained_at, seed, classifier: {auc, brier, n_train, n_test} \| null, regressor: {mae_h, n_train, n_test} \| null, feature_importance: [{name, label, importance}]}`: только чтение, метрики из `data/model_report.json`. `summary` — строка «Активен предиктор: …» (при откате — причина; та же строка в логе при старте, при откате — warning). На сервере работает только классификатор; сдвиг и задержки — расчёт; регрессор — только проверка |
| POST | `/demo/fail_next_pass` (только демо) | — | `{ok: true}`; следующий выпуск пропуска сорвётся → груз получает `pass_state: reissue_pending`, старый пропуск активен, повтор через `/shipments/{id}/pass/retry` |

Аккаунты: `X-API-Key` по-прежнему обязателен на всех `/api/*`, включая `/auth/*`; Bearer-токен (JWT HS256 на 7 дней, ключ из `JWT_SECRET`) нужен для `/auth/me` (имя, роль, права); `user` в ответах входа и `/auth/me` — `{id, name, email, role, permissions}`, права логиста `["run_scenario", "reset_demo", "decide_alert"]`, экспедитора `[]`. Если запрос пришёл с этим Bearer, сервер проверяет права: `accept`, `reject`, `reroute` — `decide_alert`; `POST /scenarios` — `run_scenario`; все `/demo/*` — `reset_demo`; нет права — 403 `forbidden_role`, неверный токен — 401 `invalid_token`. Запросы только с `X-API-Key` работают как раньше. Сессия мини-приложения и кнопки бота — права логиста; имя пользователя Telegram попадает в `accepted_by`. Пароль хранится только как хэш scrypt с солью в `data/accounts.json` (не в git), аккаунты переживают `demo/reset` и перезапуск. Демо-аккаунты создаются при первом старте: `logist@demo.ru` и `expeditor@demo.ru`, пароль `demo123`.

| POST | `/tg/auth` (без `X-API-Key`) | `{init_data}` — `Telegram.WebApp.initData` | `{token, expires_at, user: {id, name, username}, company}`; подпись initData по токену бота, срок 24 ч; 401 `invalid_init_data` / `init_data_expired`, 503 — на сервере нет токена бота. Сессия на 24 ч |

WebSocket `/ws?api_key=<ключ>` (или `/ws?token=<сессия мини-приложения>`; без них — 403), сообщения `{type, payload}`:
`shipment.updated` (Shipment), `alert.created` (Alert), `alert.updated` (Alert), `ledger.appended` (Block), `stats.updated`, `weather.updated`, `demo.reset`.
У `demo.reset` payload `null`, приходит первым после `POST /demo/reset` — клиент сбрасывает всё локальное (выбор, открытые окна, кэш) и перезапрашивает состояние.
У `weather.updated` payload `null` — клиент перезапрашивает `GET /weather`. При обрыве WS клиенты опрашивают `/shipments`, `/alerts`, `/stats` раз в 3 с.

Пример `Risk`:
```json
{"miss_probability": 0.82, "level": "high",
 "departure_shift_h": 18, "arrival_delay_h": 48,
 "factors": [{"name": "wave_height", "label": "Волна 3,4 м", "impact_hours": 11},
             {"name": "port_congestion", "label": "Загрузка порта 85%", "impact_hours": 5},
             {"name": "customs_queue", "label": "Очередь на таможне", "impact_hours": 2}]}
```

## 6. Структура репозитория

```
backend/  app/{main,models,state,graph,predictor,dispatcher,documents,ledger,weather}.py
          app/bot/  data/{seed.json,history.csv,model.cbm,model_shift.cbm,model_report.json,wave_history.json,backtest.json}
          scripts/{gen_history,train,gen_mocks,backtest}.py
          app/miniapp/ (Telegram Mini App)  deploy/ (настройка VPS, проверки)  scripts/{deploy.ps1,gen_mocks}
website/  mobile/   docs/{PLAN.md,DEMO_SCENARIO.md,FLUTTER_CONTRACT.md,design/,pitch/}   CLAUDE.md
.github/workflows/deploy.yml
```

## 7. Роли

- **Тимлид (Claude Code):** backend целиком + бот + питч.
- **Фронтендер (Cursor):** `website/`. Бэкенд развёрнут; моки `backend/data/mock/*.json` — для офлайн-разработки, всегда на формуле.
- **Flutter (Cursor):** `mobile/`. Экраны: список грузов → груз (этапы, риск) → документ (камера → поля → QR). Исходную копию каждого пропуска (токен, `doc_hash`, `block_hash`) хранить локально и не перезаписывать при обновлении с сервера: новый пропуск сохраняется рядом, старый остаётся в истории.
- **Дизайнер:** UI-кит, экраны веба и мобилки, слайды.
- **Пятый:** `seed.json` (узлы, расстояния, тарифы), проверка коэффициентов CO₂ и порогов волны, 3 демо-инвойса, тестирование, видео-бэкап.

## 8. Правила

- Контракт из раздела 5 не менять молча. Нужно поле — пиши тимлиду.
- Ветки `feat/<кто>-<что>`, в `main` только рабочее. Перед мержем — запустить.
- Все имена полей — snake_case, как в разделе 4.
- Секреты только в `.env`, в репозиторий не коммитить.
- Никаких новых тяжёлых зависимостей (Neo4j, Kafka, настоящий блокчейн) — не успеем.
- Сначала сквозной сценарий демо, потом красота. Фича, которой нет в сценарии демо, — после заморозки не делается.
- За 3 часа до конца — заморозка кода: только баги и демо.

## 9. Демо-данные и единые подписи

Главный сценарий — лёд на Северном Каспии (`ice_north`), шторм — стресс-тест: за 12 месяцев волна у Астрахани не превышала 1,44 м (`docs/DEMO_SCENARIO.md`, раздел 0). Слова для льда: «Лёд на Северном Каспии», «канал закрыт для проводки»; в ледовых текстах нет «волна» и «шторм». Тексты по типу угрозы — только из `app/hazards.py`.

Грузы (как в макете): №01 Зерно 60 т Москва → Мумбаи; №02 Металл 40 т Самара → Мумбаи; №03 Оборудование 20 т Саратов → Мумбаи; №04 Текстиль Баку → Мумбаи; №05 Удобрения Астрахань → Энзели (этап `planned`, пропуска нет — на нём показываем съёмку инвойса). Грузы №01–03 идут на один паром А Астрахань → Энзели.

Расписание, лёд, деньги и CO₂ — строго по `docs/DEMO_SCENARIO.md`. Ключевые числа для груза №01: риск 99% на льду (CatBoost; формула — 82%, шторм — 82%), отправление на 18 ч позже планового рейса, бездействие +48 ч, через Махачкалу +6 ч, расчётная экономия 298 320 ₽. По трём грузам: 126 груз-часов, 596 640 ₽.

Подписи одинаковые на всех платформах:
- статусы: Запланирован ⚪, В пути 🔵, Под риском 🔴, Перестроен 🟢, Доставлен ✅;
- база сравнения только двух видов: «к плану» и «против ожидания следующего рейса»;
- до наступления события — «расчётная экономия»;
- 125 ₽/т·ч — «условная стоимость часа задержки»;
- числа: «+18 ч», «298 тыс ₽», «−6,7% CO₂», «82%»; время «12 ноя, 14:30».

Карта: Leaflet 1.9 (`website/src/components/RealMap.tsx`) с растровой подложкой OpenStreetMap; узлы по `lat/lon` из `/api/graph`, рёбра по `Edge.path`, зона шторма по `Scenario.zone` — координат в коде сайта нет. Подложка следует теме сайта (`data-theme` на `<html>`: тёмная по умолчанию, светлая — переключателем в шапке, выбор в `localStorage`): своей тёмной нет, в тёмной теме OSM приглушается фильтром. Адреса тайлов — `NEXT_PUBLIC_TILE_URL_LIGHT`, `_DARK`, `_FALLBACK` (CARTO без ключа отдаёт водяной знак, с ключом подключается этими переменными). Цепочка: основная подложка → запасная (`tile.openstreetmap.de`) → прежняя SVG-схема, если за 5 с не пришёл ни один тайл. Атрибуция OSM в углу карты обязательна. По умолчанию вид на Каспий от Волгограда до Тегерана, кнопка «Весь коридор» — до Мумбаи; дальние концы — стрелки у края; над картой линейная схема этапов выбранного груза. Иконки из `docs/design/` перевести на `stroke="currentColor"`.

Свежесть данных: «Погода обновлена N мин назад»; старше часа — жёлтая пометка; в подвале «Расписание и загрузка портов — демо-данные».

## 10. Условия готовности демо

1. Сайт, бот и приложение показывают один маршрут, один пропуск и одну расчётную экономию.
2. Одновременное «Принять» с сайта и из Telegram создаёт одно решение и один резерв.
3. Сбой переоформления виден; после повтора нет лишних пропусков и повторной экономии.
4. `POST /api/demo/reset` возвращает исходное состояние, повторный прогон даёт те же числа.

## 11. Порядок работ

Обязательный минимум (к контрольной точке): шторм на севере → алерт на сайте и в боте → «Принять» → маршрут, счётчики и пропуск обновились на трёх платформах. Экраны W1, W2, W4, W5; бот: алерт и ответ; приложение: M1, M2, M5.

После контрольной точки, по порядку: W3, реестр W6 с подделкой записи, съёмка инвойса (M3, M4), ползунок времени на карте (`GET /api/timeline?hours=48` → позиции грузов и волна по часам), строка о загрузке порта в алерте. В последнюю очередь: шторм на всём море, фарси.

Чтобы расширения встали без переделок: у каждого этапа хранить плановое и прогнозное время, прогноз волны хранить почасовым.
