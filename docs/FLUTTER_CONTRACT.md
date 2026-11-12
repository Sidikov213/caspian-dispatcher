# Каспийский диспетчер — контракт для Flutter и единый дизайн-стандарт

Сверка `CLAUDE.md`, `docs/DEMO_SCENARIO.md`, `backend/README.md` с реальными моделями Pydantic и роутами FastAPI (ветка `main`, коммит `e62387a`). Разделено: **реализовано** · **согласовано тимлидом** · **запланировано**.

---

## 1. Что реализовано, что нет

### Реализовано в бэкенде

| Поле / механизм | Где и тип | Статус |
|---|---|---|
| `Risk.probability_drivers` | `list[{name, label, impact_pp}] \| null` | есть; заполнено только при CatBoost и маршруте с паромом, иначе `null` |
| `Scenario.starts_in_h`, `Alert.starts_in_h` | число, часы от `sim_now` | есть, сервер отдаёт всегда; storm_north и storm_full — 36, congestion_astrakhan — 18 |
| `Alert.options` | `list[AlertOption]`, по умолчанию `[]` | есть, до 3 вариантов, рекомендованный первый |
| `option_id` в `POST /alerts/{id}/accept` | необязательный | есть: 404 `option_not_found`, 422 `use_reject` для `wait` |
| `Alert.source` | `"forecast" \| "scenario" \| null` | есть |
| `Alert.status_note` | `string \| null` | есть: «угроза снята», «прогноз изменился…», «предложение устарело: …» |
| `stats.co2_saved_pct` | число | есть, сервер отдаёт всегда; `6.9` = «−6,9% CO₂» |
| `/api/auth/register`, `/login`, `/me` | — | есть |
| `/api/model`, `/api/demo/check` | — | есть |
| Наблюдатель угроз (алерт без сценария) | — | есть |
| Продакшен `https://caspian-dispatcher.ru` (запасной `https://129-101-122-103.sslip.io`) | HTTPS, WebSocket | есть; на сервере только бэкенд, сайта там нет |

### Запланировано, не реализовано

Telegram Mini App и `/tg/`, `POST /api/tg/auth`, второй способ авторизации, `Shipment.manual`, `PUBLIC_URL` / `DEMO_COMPANY`, кнопка «Открыть пульт» в боте, сайт на сервере, `GET /api/timeline`, распознавание документов vision-LLM (сейчас для любого груза отдаётся закэшированный черновик демо-инвойса).

### Расхождения документации с кодом

- `DEMO_SCENARIO.md`: риски №01–03 — 82/74/68 %, живой CatBoost даёт **82/77/68 %**. Допуск ±5 п. п. и порядок №01 > №02 > №03 записаны в `CLAUDE.md` и проверяются в `/demo/check`, но в самом сценарии не упомянуты. В интерфейсе — ровно то, что пришло из API.
- `CLAUDE.md`, раздел 5: у `weather.updated` не указан payload. Фактически **`null`** — по нему клиент перезапрашивает `GET /api/weather`. У `stats.updated` payload — объект Stats.

---

## 2. Нужна ли Flutter авторизация через `/api/auth/*`

**Согласовано тимлидом:** нет. Для работы достаточно `X-API-Key`, он обязателен на всех `/api/*`, включая `/api/auth/*`. Bearer-токен от `/auth/login` ничего не открывает в API — он только для `GET /api/auth/me` (имя и роль в шапке). Ролевых ограничений на сервере нет. На защите — кнопка «Демо-вход» под `expeditor@demo.ru` / `demo123`. Без экрана входа приложение работает так же.

---

## 3. Не противоречат ли изменения сценарию «шторм → решение → новый пропуск»

Цепочка цела. Принятие под общей блокировкой резервирует место на пароме М, выпускает новый пропуск `pass-0N-r1` на Махачкалу, старый получает `reissued`, в реестре блоки `reissued`, создаётся одна запись Decision. Сбой выпуска → `pass_state: reissue_pending`, повтор — `POST /shipments/{id}/pass/retry`. Наблюдатель меняет только **кто** создаёт алерт; числа storm_north прежние, тесты зелёные.

Учесть в клиенте:

1. **Алерт может прийти без сценария** (`source: "forecast"`) на настоящей погоде; по такому шторму сдвиг меньше (+7 ч вместо +18 ч). После запуска storm_north прогнозный алерт станет `superseded`, придёт новый со `source: "scenario"`. Показывать последний алерт со статусом `new`.
2. **Алерт может закрыться без решения:** `status: "superseded"` + `status_note: "угроза снята"`. Это не ошибка и не «устарело — смотри новый».
3. **Сайт после `e62387a` светлый** (`--color-bg: #f5f7fb`) — расходится с тёмным брендбуком и «тёмной подложкой» карты из раздела 9. Сценарию не мешает, но на проекторе сайт и приложение будут разными.

---

## 4. Устаревшие положения `CLAUDE.md`

1. Раздел 3 (схема) и раздел 9: «web (React/Vue + Leaflet)», «Карта: настоящая (Leaflet, тёмная подложка)». Фактически Next.js 16, схематичная SVG-карта с координатами в коде (`lib/map/layout.ts`); Leaflet нет, подложка светлая.
2. Раздел 6: `web/` — в репозитории `website/`; папки `mobile/` пока нет. Не упомянуты `backend/deploy/`, `.github/workflows/deploy.yml`, `backend/scripts/{deploy.ps1,gen_mocks.py}`.
3. Раздел 3: «vision-LLM» в `documents.py` и «LLM пишет текст алерта». Текст алерта всегда из шаблона, документы — из закэшированного черновика. LLM — только для вопросов в боте и только при заданном `LLM_API_KEY`.
4. Раздел 3, «Состояние в памяти»: не сказано, что аккаунты и привязки бота в файлах (`data/accounts.json`, `data/users.json`) и переживают reset.
5. Раздел 9: «Иконки из `docs/design/` перевести на `stroke="currentColor"`» — в `docs/design/` только логотип и три иконки транспорта; у сайта свой набор.
6. Раздел 11: «ползунок времени (`GET /api/timeline`)» — не сделан.
7. Раздел 5: «Если WS не успеваем — опрос…». WS готов; важнее, что подключаться надо с `?api_key=`, иначе 403. Сайт сейчас подключается без ключа и живёт только на опросе.
8. Раздел 7: «До готовности бэкенда — `backend/data/mock/*.json`». Бэкенд развёрнут; моки остались для офлайн-разработки и всегда на формуле (82/74/68).
9. Раздел 2: нет продакшен-адреса и того, что бот работает только на сервере (это есть в `backend/README.md`).

---

## А. Актуальный контракт для Flutter

### Подключение

- База: `https://caspian-dispatcher.ru/api`, заголовок `X-API-Key: <ключ из чата>` на каждом запросе. Не `caspian-dev-key` — он только для локального запуска.
- WebSocket: `wss://caspian-dispatcher.ru/ws?api_key=<ключ>`. Сообщения `{type, payload}`:

| `type` | `payload` | Что делать |
|---|---|---|
| `shipment.updated` | Shipment | обновить груз |
| `alert.created`, `alert.updated` | Alert | обновить алерт |
| `ledger.appended` | Block | дописать в реестр |
| `stats.updated` | Stats | обновить счётчики |
| `weather.updated` | **`null`** | перезапросить `GET /weather` |
| `demo.reset` | **`null`** | демо сброшено: забыть открытые экраны и кэш сервера, перезапросить всё (локальную историю пропусков не трогать) |

- При обрыве WS — опрос `/shipments`, `/alerts`, `/stats` раз в 3 с.
- Время — UTC ISO 8601, показывать в `Europe/Moscow`.
- Ошибки: `{"error": {"code", "message", "fields"?}}`; `fields` — поля запроса с ошибкой (есть у `document_invalid`).

### Эндпоинты для экспедитора

| Метод и путь | Запрос | Ответ |
|---|---|---|
| `GET /shipments?owner_tg_id=` | — | `[Shipment]` |
| `GET /shipments/{id}` | — | `Shipment` |
| `GET /shipments/{id}/alternatives` | — | `[{route, risk, delta: {hours, rub, co2_kg}, recommended}]` — только показ |
| `POST /documents` | multipart: `shipment_id`, `file` | `Document` (`status: draft`); 409 `document_confirmed` |
| `POST /documents/{id}/confirm` | `{fields}` | `{document, pass, block}`; 422 `document_invalid` + `error.fields`: обязательные `goods, hs_code, weight_kg, value, origin_country`; `weight_kg > 0` и ±5% от заявки; `value > 0`; `currency` из `USD, EUR, RUB, CNY, IRR, AZN, KZT, TMT, INR, AED, TRY`; `hs_code` — 6–10 цифр |
| `GET /passes?shipment_id=` | — | `[Pass]` — все пропуска груза, включая переоформленные, новые сверху (вкладка «Пропуска») |
| `GET /passes/{id}` | — | `Pass` |
| `POST /passes/verify` | `{token}` | `{valid, shipment_id, checkpoint_node, reason}` |
| `POST /shipments/{id}/pass/retry` | — | `{shipment, pass}`; 503 `pass_issue_failed` |
| `GET /alerts?status=` | — | `[Alert]` — только показ |
| `GET /stats` | — | `Stats` |
| `GET /weather` | — | `{updated_at, stale, source: "open-meteo"\|"cache", points: [{node_id, wave_height_m, wind_ms, forecast: [{ts, wave_height_m}]}]}` |
| `GET /graph` | — | `{nodes, edges}` — названия узлов для подписей |
| `POST /auth/login` (по желанию) | `{email, password}` | `{token, user: {id, name, email, role, permissions}}`; 401 `invalid_credentials` |
| `GET /auth/me` (по желанию) | `Authorization: Bearer <token>` | `{id, name, email, role, permissions}`; 401 `invalid_token` |

### Модели (имена полей точные)

**Shipment**: `id`, `title`, `cargo_type`, `weight_t`, `owner_tg_id?`, `origin`, `destination`, `stage: planned|in_transit|delivered`, `risk_level: low|medium|high`, `rerouted: bool`, `display_status: planned|in_transit|at_risk|rerouted|delivered`, `position: Position|null`, `current_leg: int|null`, `route: Route`, `planned_eta`, `eta`, `risk: Risk`, `pass_id: string|null`, `pass_state: none|active|reissue_pending`.

**Position** (новое, необязательно для приложения): `lat`, `lon`, `edge_id`, `mode: rail|road|sea`, `progress: 0..1`, `heading_deg`, `from_node`, `to_node`, `eta_next_node`, `waiting: bool`, `waiting_reason?: sailing|border|transfer|blocked|arrived`, `waiting_label?` («Ждёт рейс», «Граница и таможня», «Перегрузка», «Участок закрыт», «Конечный пункт»). Считает сервер от часов просмотра (`/demo/playback`; без просмотра — sim_now), статус и ETA — всегда от sim_now; у запланированного и доставленного груза `position: null` — раньше у запланированного была точка узла отправления, модель должна принимать null.

**Route**: `id`, `legs`, `total_hours`, `total_cost_rub`, `total_co2_kg`, `branch: west|transcaspian|east`.

**Leg**: `index`, `edge_id`, `from`, `to`, `mode: rail|sea|road`, `sailing_id: string|null`, `planned_start`, `planned_end`, `predicted_delay_h`, `status: done|active|pending|blocked`.

**Risk**: `miss_probability` (0..1), `level`, `departure_shift_h`, `arrival_delay_h`, `factors: [{name, label, impact_hours}]`, `probability_drivers?: [{name, label, impact_pp}] | null`.

**Alert**:
- `id`, `scenario_id`, `created_at`, `starts_in_h`, `severity: "high"|"medium"`, `title`, `text`, `status: new|accepted|rejected|superseded`;
- `items: [{shipment_id, action: reroute|wait, from_route, to_route|null, sailing_id|null, delay_vs_plan_h, saved_hours, saved_rub, co2_delta_kg}]`;
- `totals: {saved_hours, saved_rub, co2_delta_kg, co2_delta_pct}`, `do_nothing: {delay_hours, loss_rub}`, `port_load: {node_id, before, after} | null`;
- `options: [{id, title, route|null, delay_vs_plan_h, saved_hours, saved_rub, co2_delta_kg, recommended}]`;
- `source?: forecast|scenario|null`, `status_note?: string|null`, `accepted_at|null`, `accepted_via: web|telegram|null`, `accepted_by?: {name, role}|null`.

**Stats**: `saved_hours` (груз-часы), `saved_rub`, `co2_saved_kg`, `co2_saved_pct`, `decisions`, `shipments_total`, `at_risk`.

**Pass**: `id`, `shipment_id`, `checkpoint_node`, `token` (JWT), `doc_hash`, `block_hash`, `valid_until`, `status: active|reissued|revoked`.

**Document**: `id`, `shipment_id`, `type: invoice|cmr|packing_list`, `source_lang`, `image_url|null`, `fields: {seller, buyer, goods, hs_code, weight_kg, value, currency, origin_country}` (все nullable), `checks: [{name, ok, note}]`, `status: draft|confirmed`, `hash|null`.

**Block**: `index`, `ts`, `event: issued|reissued|verified`, `shipment_id`, `checkpoint_node`, `doc_hash`, `prev_hash`, `hash`.

### Поля после первой версии контракта

**Согласовано:** для клиента все необязательные. Нет поля или `null` → блок не показывается, ничего не подставлять и не вычислять.

| Поле | Наличие в ответе сервера | Если нет |
|---|---|---|
| `Risk.probability_drivers` | может быть `null` (формула, суша) | не показывать «Что повлияло на вероятность» |
| `Alert.starts_in_h`, `Scenario.starts_in_h` | всегда есть | не показывать «через N ч» |
| `Alert.options` | всегда массив, может быть пустым | не показывать варианты |
| `Alert.source` | есть у новых алертов | не показывать источник |
| `Alert.status_note` | `null`, пока алерт открыт | у закрытого — только статус |
| `Stats.co2_saved_pct` | всегда есть | не показывать процент CO₂ |
| `Node.facts`, `Node.sources` | только у портов с проверенными фактами (Махачкала, Астрахань) | не показывать факты |
| `GET /data-sources` | по желанию: источники данных и их тип (real / modeled / synthetic) | — |
| `Alert.hazard` | у новых алертов: `ice` \| `storm` \| `congestion` \| `customs` | значок и слова угрозы по `title`; слово «шторм» в коде не писать |
| `Alert.card` | у новых алертов | показывать `title`/`text` как раньше |
| `Scenario.hazard`, `Scenario.note` | у новых сценариев; `note` у шторма — «Стресс-тест: …» | не показывать |
| `Alert.accepted_by` | есть, если решение принято с входом сайта, из мини-приложения или бота | «через сайт» / «через Telegram» по `accepted_via` |
| `user.permissions` | всегда есть в `/auth/*` | экспедитор: `[]` |

### Карточка алерта (`Alert.card`) и тип угрозы (`hazard`)

Главный сценарий демо — лёд (`hazard: "ice"`), шторм — стресс-тест. Тип угрозы брать только из `Alert.hazard` / `card.kind`, слова — с сервера.

`card` — готовые строки, клиент рисует как есть, ничего не считает:
- `kind` — тип угрозы (значок: лёд, шторм, затор, таможня); `headline` — «Лёд на Северном Каспии»; `subtitle` — «3 груза под риском»;
- `period` — «14 ноя, 02:00–21:00» по Москве; `metrics[]` — `{key, label, value}`, набор по типу угрозы (лёд: «Волго-Каспийский канал — закрыт для проводки», «Закрытие порта — 11 ч»; шторм: волна и предел парома; затор: загрузка порта);
- `route` — `{sailing_label, from, to, departure}`; `impact` — `{shipments, weight_t, max_risk_pct}`; `note` — у шторма «Стресс-тест: …»;
- `decision` — `null` до решения; после — `{status, title, detail: "+6 ч к плану", via, via_label, accepted_by_name}`.

### Пуш-уведомления (FCM)

Сервер шлёт пуши через Firebase Cloud Messaging, проект `caspian-dispatcher`, по тем же событиям, что Telegram-бот.

1. После входа (`POST /auth/login`) и разрешения уведомлений: `FirebaseMessaging.instance.getToken()` → `POST /api/devices` `{token, platform: "ios" | "android"}` с `X-API-Key` **и** `Authorization: Bearer <token из /auth/login>`. Ответ `{ok, push_enabled}`; `push_enabled: false` — на сервере нет ключа Firebase, пуши не придут.
2. `FirebaseMessaging.instance.onTokenRefresh` → тот же `POST /api/devices` с новым токеном.
3. Выход из аккаунта → `DELETE /api/devices` `{token}` (с Bearer), потом забыть токен входа.
4. Пуш: `notification {title, body}` + `data {type: "alert.created" | "alert.updated", alert_id, status}`. `alert.created` — новая угроза (заголовок — `Alert.title`), `alert.updated` со `status: "accepted"` — решение принято. По тапу открыть груз из алерта (`GET /alerts` → `items[].shipment_id`).
5. Android: канал уведомлений `alerts` (high importance) создать при старте — сервер шлёт `channel_id: "alerts"`. iOS: APNs-ключ загрузить в Firebase Console → Cloud Messaging.
6. `google-services.json` и `GoogleService-Info.plist` — из Firebase Console, в git не класть.

### Правила для экспедитора

- **Согласовано:** экспедитор решений не принимает. `accept`, `reject`, `option_id` в приложении не вызываются. `Alert.options` — только показ «что предложено» (рекомендованный первый, `recommended: true`) и «что принято» (после `status: accepted` рекомендованным помечен принятый вариант, `items` и `totals` описывают его).
- Статус груза — **только** из `display_status`, клиент его не вычисляет.
- Пропуска хранить локально (`CLAUDE.md`, раздел 7): исходную копию (`token`, `doc_hash`, `block_hash`) не перезаписывать; новый пропуск после переоформления сохраняется рядом.

### Что сделать во Flutter

- Базовый адрес и ключ — из настроек сборки, не в коде.
- WebSocket — с `?api_key=`.
- Обработать `weather.updated` с `payload: null`.
- Обработать `status_note` («угроза снята», «заменён алертом …», «по этим грузам решение уже принято»): показывать текстом как есть.
- Обработать `demo.reset`.
- Вкладка «Пропуска» — `GET /passes?shipment_id=`.
- Если приложение шлёт `Authorization: Bearer` экспедитора, `accept`/`reject`/сценарии/`/demo/*` отвечают 403 `forbidden_role` — их и так не вызываем.
- Скрывать блоки при отсутствии необязательных полей.
- По желанию — экран входа с кнопкой «Демо-вход».

---

## Б. Единый дизайн-стандарт (Minimal V2, сайт и Flutter)

### Цвета

| Роль | HEX |
|---|---|
| Фон | `#0B1220` |
| Поверхность (карточки, панели) | `#131C2E` |
| Граница | `#24304A` |
| Текст | `#E6EDF7` |
| Вторичный текст | `#8A97AD` |
| Акцент (кнопки, ссылки, выбор) | `#2F80ED` |
| Бирюза — **только** линии и прогресс | `#3FE0C5` |

### Статусы (`display_status`): подпись + цвет + значок

| Значение | Подпись | Цвет |
|---|---|---|
| `planned` | Запланирован ⚪ | `#8A97AD` |
| `in_transit` | В пути 🔵 | `#3B82F6` |
| `at_risk` | Под риском 🔴 | `#EF4444` |
| `rerouted` | Перестроен 🟢 | `#22C55E` |
| `delivered` | Доставлен ✅ | `#8A97AD` + галочка |

### Уровни риска (`level`)

Низкий `#22C55E`, средний `#F59E0B`, высокий `#EF4444`. Статус и уровень риска всегда подписаны текстом, не только цветом.

### Типографика

Inter. Основной текст не меньше 15 px. Ключевые числа (риск %, часы, ₽) не меньше 28 px, жирные, табличные цифры.

### Сетка и формы

Шаг 8 px, все отступы кратны 8. Скругление карточек 12 px, кнопок 8 px. Высота кнопок 52 px.

### Компоненты

- **Карточка груза:** номер, название, маршрут «откуда → куда», метка статуса, риск %.
- **Двойник:** риск крупно; «отправление на N ч позже планового рейса»; «если рейс отменят: прибытие +N ч»; причины из `factors`; «что повлияло» из `probability_drivers`; этапы «план / прогноз»; CO₂; пропуск.
- **Алерт:** две колонки «Ничего не делать» и «Решение диспетчера», варианты из `options`.
- **Пропуск:** QR, пункт пропуска, срок, статус; при `reissue_pending` — плашка «Пропуск ожидает переоформления, действует старый».

### Тексты и числа (`CLAUDE.md`, раздел 9)

- Формат: «+18 ч», «298 тыс ₽», «−6,7% CO₂», «82%», время «12 ноя, 14:30» по Москве.
- База сравнения — только «к плану» и «против ожидания следующего рейса».
- До события деньги и часы — «расчётная экономия», часы — «груз-часы». 125 ₽/т·ч — «условная стоимость часа задержки».
- Свежесть: «Погода обновлена N мин назад»; старше часа или `stale: true` — жёлтая пометка. В подвале: «Расписание и загрузка портов — демо-данные».

### Сайт и этот стандарт

- Тёмная тема сайта (по умолчанию) — цвета этого стандарта на CSS-переменных (`website/src/app/globals.css`); светлая — прежняя палитра сайта, включается переключателем в шапке.
- Бирюза — только линии маршрутов и полосы прогресса (загрузка рейсов, важность признаков).
