"""«Каспийский диспетчер» — бэкенд. Контракт — раздел 5 CLAUDE.md.

Состояние — в памяти (state.py), расчёт — dispatcher.py. Моки в data/mock/ строит scripts/gen_mocks.py
этим же движком, для тех, кто читает файлы напрямую.
Запуск: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import (APIRouter, Depends, FastAPI, File, Form, Query, Request, UploadFile,
                     WebSocket, WebSocketDisconnect)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import events
from . import models as M
from .bot import start_bot, stop_bot
from .auth import Accounts
from .config import ACCOUNTS_PATH, API_KEY, MINIAPP_DIR, WEATHER_MODE
from .democheck import log_check, run_check
from .modelinfo import log_active, model_info
from .state import ApiError, state
from .tgauth import issue_session, session_ok, verify_init_data

log = logging.getLogger("caspian")
for _name in ("caspian", "aiogram"):  # uvicorn настраивает только свои логгеры; боту нужен свой вывод
    _lg = logging.getLogger(_name)
    if not _lg.handlers:
        _h = logging.StreamHandler()
        _h.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
        _lg.addHandler(_h)
        _lg.setLevel(logging.INFO)


# Аккаунты живут отдельно от состояния демо: demo/reset их не трогает. Демо-аккаунты — при первом старте.
accounts = Accounts(ACCOUNTS_PATH)


async def refresh_weather() -> bool:
    """Свежий прогноз Open-Meteo → погода и риски в состоянии, событие weather.updated."""
    ok = await state.forecast.refresh()
    async with state.lock:
        state.on_forecast_updated()
    await flush()
    return ok


async def weather_loop() -> None:
    from .weather import REFRESH_S
    while True:
        await asyncio.sleep(REFRESH_S)
        try:
            await refresh_weather()
        except Exception:
            log.exception("обновление погоды упало")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Бот живёт в процессе бэкенда: polling как asyncio-задача. Без BOT_TOKEN сервер работает без бота.
    Погода (WEATHER_MODE=live) обновляется раз в 30 мин; перед первой проверкой демо ждём первый прогноз."""
    weather_task = None
    if not state.forecast.synthetic:
        try:
            ok = await asyncio.wait_for(refresh_weather(), timeout=30)
            log.info("Погода: %s", "Open-Meteo" if ok else "Open-Meteo недоступен, работаем по кэшу")
        except asyncio.TimeoutError:
            log.warning("Погода: Open-Meteo не ответил за 30 с, работаем по кэшу")
        weather_task = asyncio.create_task(weather_loop(), name="weather-refresh")
    else:
        log.info("Погода: WEATHER_MODE=%s — синтетический прогноз, сеть не трогаем", WEATHER_MODE)
    log.info("Сценарий: sim_now %s", state.sim_now.isoformat())
    log_active(state.predictor)
    log_check(state, "старт")
    runtime = await start_bot(state)
    try:
        yield
    finally:
        await stop_bot(runtime)
        if weather_task:
            weather_task.cancel()


app = FastAPI(
    lifespan=lifespan,
    title="Каспийский диспетчер API",
    version="0.2.0",
    description="Контракт — раздел 5 CLAUDE.md. Ответы считает движок сценария (состояние в памяти). "
                "Нажмите **Authorize** и введите X-API-Key из `backend/.env`.",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------- ошибки: {"error": {"code", "message"}} ----------

def err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@app.exception_handler(ApiError)
async def _api_error(_: Request, e: ApiError):
    return err(e.status, e.code, e.message)


@app.exception_handler(StarletteHTTPException)
async def _http_error(_: Request, e: StarletteHTTPException):
    if isinstance(e.detail, dict) and "code" in e.detail:
        return err(e.status_code, e.detail["code"], e.detail["message"])
    return err(e.status_code, "http_error", str(e.detail))


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, e: RequestValidationError):
    first = e.errors()[0] if e.errors() else {}
    loc = ".".join(str(x) for x in first.get("loc", []))
    return err(422, "validation_error", f"{loc}: {first.get('msg', 'неверный запрос')}")


# ---------- X-API-Key ----------

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def key_ok(key: str | None) -> bool:
    return bool(API_KEY) and key is not None and secrets.compare_digest(key, API_KEY)


tg_bearer = HTTPBearer(auto_error=False)


async def require_key(key: str | None = Depends(api_key_header),
                      cred: HTTPAuthorizationCredentials | None = Depends(tg_bearer)):
    """Доступ к /api/*: X-API-Key (сайт, приложение, бот, тесты) или сессия мини-приложения Telegram
    (Authorization: Bearer <токен из POST /api/tg/auth>). Токен входа сайта (/api/auth) доступа не даёт."""
    if key_ok(key):
        return
    if cred and session_ok(cred.credentials):
        return
    if not API_KEY:
        raise ApiError(500, "server_misconfigured", "API_KEY не задан в backend/.env")
    raise ApiError(401, "unauthorized", "Нужен заголовок X-API-Key")


# ---------- WebSocket /ws?api_key=... ----------

class Hub:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def send(self, type_: str, payload):
        dead = []
        for ws in self.clients:
            try:
                await ws.send_json({"type": type_, "payload": payload})
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


hub = Hub()
WS_TYPES = {"shipment.updated", "alert.created", "alert.updated", "ledger.appended", "stats.updated",
            "weather.updated"}


async def _to_ws(type_: str, payload) -> None:
    if type_ in WS_TYPES:
        await hub.send(type_, payload)


events.subscribe(_to_ws)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket, api_key: str | None = None, token: str | None = None):
    if not (key_ok(api_key or ws.headers.get("x-api-key")) or session_ok(token)):
        await ws.close(code=1008)
        return
    await ws.accept()
    hub.clients.add(ws)
    try:
        while True:
            await ws.receive_text()  # клиенту писать не нужно, держим соединение
    except WebSocketDisconnect:
        hub.clients.discard(ws)


async def flush():
    """Раздать накопленные события: WebSocket и Telegram-бот."""
    await events.flush(state)


# ---------- служебное ----------

@app.get("/health", include_in_schema=False)
async def health():
    return {"ok": True, "sim_now": state.sim_now.isoformat(), "time": datetime.now(timezone.utc).isoformat()}


# ---------- API ----------

api = APIRouter(prefix="/api", dependencies=[Depends(require_key)],
                responses={401: {"model": M.ErrorOut}, 404: {"model": M.ErrorOut}})


@api.get("/graph", response_model=M.GraphOut, tags=["граф"])
async def get_graph():
    return state.graph_out()


@api.get("/shipments", response_model=list[M.Shipment], tags=["грузы"])
async def list_shipments(owner_tg_id: int | None = None):
    return state.shipments_list(owner_tg_id)


@api.get("/shipments/{sid}", response_model=M.Shipment, tags=["грузы"])
async def get_shipment(sid: str):
    return state.shipment(sid)


@api.post("/shipments", response_model=M.Shipment, tags=["грузы"])
async def create_shipment(body: M.ShipmentCreate):
    """Новый груз в статусе planned; маршрут — первый допустимый путь по графу и расписанию."""
    out = await state.create_shipment(body.model_dump())
    await flush()
    return out


@api.get("/shipments/{sid}/alternatives", response_model=list[M.AlternativeOut], tags=["грузы"])
async def get_alternatives(sid: str):
    return state.alternatives(sid)


@api.post("/shipments/{sid}/reroute", response_model=M.Shipment, tags=["грузы"],
          responses={409: {"model": M.ErrorOut}})
async def reroute(sid: str, body: M.RerouteIn):
    """Ручная смена маршрута: резерв места, переоформление пропуска. Счётчики экономии не меняются."""
    out = await state.reroute(sid, body.route_id)
    await flush()
    return out


@api.post("/shipments/{sid}/pass/retry", response_model=M.PassRetryOut, tags=["пропуска"],
          responses={503: {"model": M.ErrorOut}})
async def retry_pass(sid: str):
    """Повтор переоформления (pass_state = reissue_pending). Повторный вызов новых пропусков не создаёт."""
    out = await state.retry_pass(sid)
    await flush()
    return out


@api.get("/weather", response_model=M.WeatherOut, tags=["погода"])
async def get_weather():
    return state.weather_out()


@api.get("/scenarios/presets", response_model=list[M.PresetOut], tags=["сценарии"])
async def presets():
    return state.presets()


@api.post("/scenarios", response_model=M.ScenarioCreateOut, tags=["сценарии"])
async def run_scenario(body: M.ScenarioIn):
    """Запуск сценария → конвейер диспетчера → алерт. Повторный запуск того же пресета возвращает его алерт."""
    out = await state.run_scenario(body.preset)
    await flush()
    return out


@api.get("/alerts", response_model=list[M.Alert], tags=["алерты"])
async def list_alerts(status: M.AlertStatus | None = None):
    return state.alerts_list(status)


@api.post("/alerts/{alert_id}/accept", response_model=M.AcceptOut, tags=["алерты"],
          responses={409: {"model": M.ErrorOut}})
async def accept_alert(alert_id: str, body: M.AcceptIn):
    try:
        return await state.accept(alert_id, body.via, body.option_id)
    finally:
        await flush()


@api.post("/alerts/{alert_id}/reject", response_model=M.Alert, tags=["алерты"],
          responses={409: {"model": M.ErrorOut}})
async def reject_alert(alert_id: str):
    out = await state.reject(alert_id)
    await flush()
    return out


@api.get("/sailings", response_model=list[M.Sailing], tags=["рейсы"])
async def list_sailings(from_: str | None = Query(None, alias="from"), to: str | None = None):
    return state.sailings_list(from_, to)


@api.post("/documents", response_model=M.Document, tags=["документы"])
async def upload_document(shipment_id: str = Form(...), file: UploadFile = File(...)):
    """Черновик документа. Распознавание vision-LLM — позже; сейчас закэшированный демо-инвойс (фарси)."""
    await file.read()
    return state.upload_document(shipment_id)


@api.post("/documents/{doc_id}/confirm", response_model=M.DocumentConfirmOut, tags=["документы"],
          responses={409: {"model": M.ErrorOut}, 422: {"model": M.ErrorOut}, 503: {"model": M.ErrorOut}})
async def confirm_document(doc_id: str, body: M.DocumentConfirmIn):
    out = await state.confirm(doc_id, body.fields.model_dump())
    await flush()
    return out


@api.get("/passes/{pid}", response_model=M.Pass, tags=["пропуска"])
async def get_pass(pid: str):
    return state.pass_(pid)


@api.post("/passes/verify", response_model=M.PassVerifyOut, tags=["пропуска"])
async def verify_pass(body: M.PassVerifyIn):
    return state.verify_pass(body.token)


@api.get("/ledger", response_model=list[M.Block], tags=["реестр"])
async def get_ledger():
    return state.ledger_list()


@api.get("/ledger/verify", response_model=M.LedgerVerifyOut, tags=["реестр"])
async def verify_ledger():
    return state.ledger_verify()


@api.post("/ledger/tamper", response_model=M.OkOut, tags=["реестр"])
async def tamper_ledger(body: M.TamperIn):
    """Только демо: портит doc_hash блока, проверка цепочки краснеет на нём."""
    state.tamper(body.index)
    return {"ok": True}


@api.get("/stats", response_model=M.StatsOut, tags=["счётчики"])
async def get_stats():
    return state.stats()


@api.post("/users/link", response_model=M.OkOut, tags=["пользователи"])
async def link_user(body: M.UserLinkIn):
    state.link_user(body.telegram_id, body.name)
    return {"ok": True}


@api.post("/demo/reset", response_model=M.OkOut, tags=["демо"])
async def demo_reset():
    async with state.lock:
        state.reset()
    for s in state.shipments_list():
        await hub.send("shipment.updated", s)
    await hub.send("stats.updated", state.stats())
    await hub.send("weather.updated", None)
    log.info("Reset: sim_now %s", state.sim_now.isoformat())
    log_check(state, "reset")
    return {"ok": True}


# ---------- Telegram Mini App: вход по initData (без X-API-Key) и статика /tg/ ----------

@app.post("/api/tg/auth", response_model=M.TgAuthOut, tags=["мини-приложение"],
          responses={401: {"model": M.ErrorOut}, 503: {"model": M.ErrorOut}})
async def tg_auth(body: M.TgAuthIn):
    """Проверка подписи initData по токену бота (срок 24 ч) → сессионный токен на 24 ч. Токен принимается
    на всех /api/* в заголовке Authorization: Bearer и в WebSocket /ws?token=."""
    return issue_session(verify_init_data(body.init_data))


@app.get("/tg", include_in_schema=False)
async def tg_root():
    return RedirectResponse("/tg/")


# ---------- аккаунты: только имя и роль для клиента; доступ к API по-прежнему по X-API-Key ----------

bearer = HTTPBearer(auto_error=False)


@api.post("/auth/register", response_model=M.AuthOut, tags=["аккаунты"],
          responses={409: {"model": M.ErrorOut}, 422: {"model": M.ErrorOut}})
async def auth_register(body: M.AuthRegisterIn):
    """Регистрация логиста или экспедитора. 409 email_taken, 422 weak_password (< 6 символов) / invalid_email."""
    return accounts.register(body.name, body.email, body.password, body.role)


@api.post("/auth/login", response_model=M.AuthOut, tags=["аккаунты"])
async def auth_login(body: M.AuthLoginIn):
    """Вход. Неверный email или пароль — 401 invalid_credentials. Демо: logist@demo.ru / expeditor@demo.ru, demo123."""
    return accounts.login(body.email, body.password)


@api.get("/auth/me", response_model=M.AuthUser, tags=["аккаунты"])
async def auth_me(cred: HTTPAuthorizationCredentials | None = Depends(bearer)):
    """Кто вошёл: по заголовку Authorization: Bearer <token>. Нет или неверный токен — 401 invalid_token."""
    return accounts.me(cred.credentials if cred else None)


@api.get("/model", response_model=M.ModelInfoOut, tags=["модель"])
async def get_model():
    """Активный предиктор, метрики на отложенной выборке, что модель делает на сервере. Обучена на
    синтетической истории: метрики показывают работу конвейера, а не точность на реальных данных."""
    return model_info(state.predictor)


@api.get("/demo/check", response_model=M.DemoCheckOut, tags=["демо"])
async def demo_check():
    """Только демо: storm_north на копии исходного состояния, сверка ключевых чисел с эталоном."""
    return run_check(state)


@api.post("/demo/fail_next_pass", response_model=M.OkOut, tags=["демо"])
async def demo_fail_next_pass():
    """Только демо: следующий выпуск пропуска завершится сбоем (груз получит reissue_pending)."""
    state.arm_pass_failure()
    return {"ok": True}


app.include_router(api)


# Мини-приложение Telegram — статика без сборки. Монтируется последним, после всех роутов.
app.mount("/tg", StaticFiles(directory=MINIAPP_DIR, html=True, check_dir=False), name="miniapp")
