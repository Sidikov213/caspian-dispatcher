"""«Каспийский диспетчер» — бэкенд. Контракт — раздел 5 CLAUDE.md.

Сейчас все эндпоинты отдают моки из data/mock/*.json (см. state.py).
Запуск: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
import secrets
from datetime import datetime, timezone

from fastapi import (APIRouter, Depends, FastAPI, File, Form, Query, Request, UploadFile,
                     WebSocket, WebSocketDisconnect)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import models as M
from .config import API_KEY
from .state import ApiError, mock, state

app = FastAPI(
    title="Каспийский диспетчер API",
    version="0.1.0-mock",
    description="Контракт — раздел 5 CLAUDE.md. Сейчас ответы — моки из `backend/data/mock/`. "
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


async def require_key(key: str | None = Depends(api_key_header)):
    if not API_KEY:
        raise ApiError(500, "server_misconfigured", "API_KEY не задан в backend/.env")
    if not key_ok(key):
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


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket, api_key: str | None = None):
    if not key_ok(api_key or ws.headers.get("x-api-key")):
        await ws.close(code=1008)
        return
    await ws.accept()
    hub.clients.add(ws)
    try:
        while True:
            await ws.receive_text()  # клиенту писать не нужно, держим соединение
    except WebSocketDisconnect:
        hub.clients.discard(ws)


async def push_shipments(ids=None):
    for s in state.shipments():
        if ids is None or s["id"] in ids:
            await hub.send("shipment.updated", s)


# ---------- служебное ----------

@app.get("/health", include_in_schema=False)
async def health():
    return {"ok": True, "phase": state.phase, "time": datetime.now(timezone.utc).isoformat()}


# ---------- API ----------

api = APIRouter(prefix="/api", dependencies=[Depends(require_key)],
                responses={401: {"model": M.ErrorOut}, 404: {"model": M.ErrorOut}})


@api.get("/graph", response_model=M.GraphOut, tags=["граф"])
async def get_graph():
    return state.graph()


@api.get("/shipments", response_model=list[M.Shipment], tags=["грузы"])
async def list_shipments(owner_tg_id: int | None = None):
    return state.shipments(owner_tg_id)


@api.get("/shipments/{sid}", response_model=M.Shipment, tags=["грузы"])
async def get_shipment(sid: str):
    return state.shipment(sid)


@api.post("/shipments", response_model=M.Shipment, tags=["грузы"])
async def create_shipment(body: M.ShipmentCreate):
    """Мок: возвращает новый груз в статусе planned, в состоянии не сохраняется."""
    base = state.shipment("sh-05")
    node = next((n for n in state.graph()["nodes"] if n["id"] == body.origin), None)
    if node is None:
        raise ApiError(404, "node_not_found", f"Узел {body.origin} не найден")
    route = {**base["route"], "id": "r-sh-06-plan", "legs": [], "total_hours": 0,
             "total_cost_rub": 0, "total_co2_kg": 0}
    return {**base, **body.model_dump(), "id": "sh-06", "route": route, "current_leg": None,
            "position": {"lat": node["lat"], "lon": node["lon"]}, "pass_id": None, "pass_state": "none"}


@api.get("/shipments/{sid}/alternatives", response_model=list[M.AlternativeOut], tags=["грузы"])
async def get_alternatives(sid: str):
    return state.alternatives(sid)


@api.post("/shipments/{sid}/reroute", response_model=M.Shipment, tags=["грузы"])
async def reroute(sid: str, body: M.RerouteIn):
    """Мок: возвращает груз с выбранным маршрутом, в состоянии не сохраняется."""
    s = state.shipment(sid)
    alt = next((a for a in state.alternatives(sid) if a["route"]["id"] == body.route_id), None)
    if alt is None:
        raise ApiError(404, "route_not_found", f"Маршрут {body.route_id} не найден")
    rerouted = not body.route_id.endswith("-plan")
    level = alt["risk"]["level"]
    return {**s, "route": alt["route"], "rerouted": rerouted, "risk": alt["risk"], "risk_level": level,
            "display_status": M.display_status_of(s["stage"], level, rerouted)}


@api.post("/shipments/{sid}/pass/retry", response_model=M.PassRetryOut, tags=["пропуска"])
async def retry_pass(sid: str):
    s = state.shipment(sid)
    if not s["pass_id"]:
        raise ApiError(404, "no_pass", f"У груза {sid} нет пропуска")
    return {"shipment": s, "pass": state.pass_(s["pass_id"])}


@api.get("/weather", response_model=M.WeatherOut, tags=["погода"])
async def get_weather():
    return state.weather()


@api.get("/scenarios/presets", response_model=list[M.PresetOut], tags=["сценарии"])
async def presets():
    return mock("scenario_presets")


@api.post("/scenarios", response_model=M.ScenarioCreateOut, tags=["сценарии"])
async def run_scenario(body: M.ScenarioIn):
    was = state.phase
    out = state.run_scenario(body.preset)
    if was == "initial":
        await hub.send("alert.created", out["alert"])
        await push_shipments()
        await hub.send("weather.updated", None)
        await hub.send("stats.updated", state.stats())
    return out


@api.get("/alerts", response_model=list[M.Alert], tags=["алерты"])
async def list_alerts(status: M.AlertStatus | None = None):
    return state.alerts(status)


@api.post("/alerts/{alert_id}/accept", response_model=M.AcceptOut, tags=["алерты"],
          responses={409: {"model": M.ErrorOut}})
async def accept_alert(alert_id: str, body: M.AcceptIn):
    out = await state.accept(alert_id, body.via)
    if not out["already_accepted"]:
        await hub.send("alert.updated", out["alert"])
        await push_shipments()
        for b in out["blocks"]:
            await hub.send("ledger.appended", b)
        await hub.send("stats.updated", state.stats())
    return out


@api.post("/alerts/{alert_id}/reject", response_model=M.Alert, tags=["алерты"],
          responses={409: {"model": M.ErrorOut}})
async def reject_alert(alert_id: str):
    a = state.reject(alert_id)
    await hub.send("alert.updated", a)
    return a


@api.get("/sailings", response_model=list[M.Sailing], tags=["рейсы"])
async def list_sailings(from_: str | None = Query(None, alias="from"), to: str | None = None):
    return state.sailings(from_, to)


@api.post("/documents", response_model=M.Document, tags=["документы"])
async def upload_document(shipment_id: str = Form(...), file: UploadFile = File(...)):
    """Мок: всегда возвращает распознанный инвойс груза №05 (фарси) в статусе draft."""
    state.shipment(shipment_id)
    await file.read()
    doc = mock("document_draft")
    doc["shipment_id"] = shipment_id
    return doc


@api.post("/documents/{doc_id}/confirm", response_model=M.DocumentConfirmOut, tags=["документы"])
async def confirm_document(doc_id: str, body: M.DocumentConfirmIn):
    out = state.confirm_document(doc_id)
    await hub.send("ledger.appended", out["block"])
    await push_shipments({out["document"]["shipment_id"]})
    return out


@api.get("/passes/{pid}", response_model=M.Pass, tags=["пропуска"])
async def get_pass(pid: str):
    return state.pass_(pid)


@api.post("/passes/verify", response_model=M.PassVerifyOut, tags=["пропуска"])
async def verify_pass(body: M.PassVerifyIn):
    return state.verify_pass(body.token)


@api.get("/ledger", response_model=list[M.Block], tags=["реестр"])
async def get_ledger():
    return state.ledger()


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
    return {"ok": True}


@api.post("/demo/reset", response_model=M.OkOut, tags=["демо"])
async def demo_reset():
    state.reset()
    await push_shipments()
    await hub.send("stats.updated", state.stats())
    return {"ok": True}


app.include_router(api)
