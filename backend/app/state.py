"""Живое состояние в памяти. Источник — data/seed.json; POST /demo/reset возвращает всё к сиду.

Все изменяющие операции, которые должны быть атомарными (accept, retry пропуска, reroute,
запуск сценария, подтверждение документа), идут под одним asyncio.Lock: одновременные «Принять»
с сайта и из Telegram дают одно решение и один резерв места.

Изменения копятся в outbox событий (`events`); main.py отправляет их в WebSocket после ответа.
"""
import asyncio
import copy
import json
import re
from pathlib import Path

import jwt

from . import dispatcher as D
from .clock import Clock
from .config import DEMO_NOW, PASS_SECRET, SEED_PATH
from .documents import doc_hash, normalize_fields
from .errors import ApiError
from .graph import Graph
from .ledger import append_block, verify_chain
from .predictor import Predictor, get_predictor
from .scenarios import PRESET_LIST
from .schedule import Ctx
from .util import iso, parse
from .weather import Weather

__all__ = ["ApiError", "State", "state"]

REQUIRED_FIELDS = ("goods", "hs_code", "weight_kg", "value", "origin_country")
WEIGHT_TOLERANCE = 0.05
HS_RE = re.compile(r"^\d{4}( ?\d{2})?( ?\d{2,4})?$")


class PassIssueError(Exception):
    """Сбой выпуска пропуска (в демо вызывается POST /api/demo/fail_next_pass)."""


class State:
    PassIssueError = PassIssueError

    def __init__(self, seed_path: Path = SEED_PATH, clock: Clock | None = None,
                 predictor: Predictor | None = None):
        self.seed_path = Path(seed_path)
        self.clock = clock or Clock(DEMO_NOW)
        self.predictor = predictor or get_predictor()
        self.lock = asyncio.Lock()
        self.reset()

    @property
    def sim_now(self):
        return self.clock.sim_now

    # ---------------- сброс ----------------

    def reset(self) -> None:
        seed = json.loads(self.seed_path.read_text(encoding="utf-8"))
        self.clock.reset()
        self.meta = seed["meta"]
        self.graph = Graph(seed["nodes"], seed["edges"], self.meta["ferry_edges"])
        self.sailings = {s["id"]: s for s in seed["sailings"]}
        self.shipments = {s["id"]: s for s in seed["shipments"]}
        self.plan_routes = {sid: copy.deepcopy(s["route"]) for sid, s in self.shipments.items()}
        self.documents = {d["id"]: d for d in seed["documents"]}
        self.demo_drafts = seed.get("demo_drafts", {})
        self.ledger: list[dict] = seed["ledger"]
        self.passes = {p["id"]: p for p in seed["passes"]}
        for p in self.passes.values():  # подпись ключом сервера; токены одинаковы при каждом reset
            p["token"] = self._sign(p["id"], p["shipment_id"], p["checkpoint_node"], p["doc_hash"],
                                    p["block_hash"], p["valid_until"])
        self.alerts: dict[str, dict] = {}
        self.alert_internal: dict[str, dict] = {}
        self.accept_results: dict[str, dict] = {}
        self.decisions: list[dict] = []
        self.scenarios: dict[str, dict] = {}
        self.users: dict[int, str] = {}
        self.fail_next_pass = 0
        self.seq = {"alert": 0, "decision": 0,
                    "shipment": max(int(s[3:]) for s in self.shipments if s[3:].isdigit())}
        self.weather = Weather(self.sim_now)
        self.events: list[tuple[str, object]] = []
        for sh in self.shipments.values():
            D.refresh_shipment(self, sh)
        self.events.clear()

    # ---------------- служебное ----------------

    def ctx(self) -> Ctx:
        return Ctx(self.graph, self.sailings, self.weather, self.meta, list(self.scenarios.values()),
                   self.sim_now)

    def emit(self, type_: str, payload) -> None:
        self.events.append((type_, copy.deepcopy(payload)))

    def drain_events(self) -> list[tuple[str, object]]:
        out, self.events = self.events, []
        return out

    def get_shipment(self, sid: str) -> dict:
        sh = self.shipments.get(sid)
        if sh is None:
            raise ApiError(404, "shipment_not_found", f"Груз {sid} не найден")
        return sh

    # ---------------- чтение ----------------

    def graph_out(self):
        return self.graph.to_api()

    def shipments_list(self, owner_tg_id: int | None = None):
        return [copy.deepcopy(s) for s in self.shipments.values()
                if owner_tg_id is None or s["owner_tg_id"] == owner_tg_id]

    def shipment(self, sid: str):
        return copy.deepcopy(self.get_shipment(sid))

    def alternatives(self, sid: str):
        return D.alternatives(self, sid)

    def weather_out(self):
        return self.weather.to_api()

    def presets(self):
        return copy.deepcopy(PRESET_LIST)

    def sailings_list(self, from_: str | None, to: str | None):
        return [copy.deepcopy(s) for s in self.sailings.values()
                if (not from_ or s["from"] == from_) and (not to or s["to"] == to)]

    def alerts_list(self, status: str | None = None):
        return [copy.deepcopy(a) for a in self.alerts.values() if not status or a["status"] == status]

    def stats(self):
        items = [i for d in self.decisions for i in d["items"]]
        sh = list(self.shipments.values())
        return {"saved_hours": sum(i["saved_hours"] for i in items),
                "saved_rub": sum(i["saved_rub"] for i in items),
                "co2_saved_kg": round(-sum(i["co2_delta_kg"] for i in items), 1),
                "decisions": len(self.decisions), "shipments_total": len(sh),
                "at_risk": sum(s["display_status"] == "at_risk" for s in sh)}

    def ledger_list(self):
        return copy.deepcopy(self.ledger)

    def ledger_verify(self):
        broken = verify_chain(self.ledger)
        return {"valid": broken is None, "broken_at": broken}

    def pass_(self, pid: str):
        p = self.passes.get(pid)
        if p is None:
            raise ApiError(404, "pass_not_found", f"Пропуск {pid} не найден")
        return copy.deepcopy(p)

    def verify_pass(self, token: str):
        try:
            claims = jwt.decode(token, PASS_SECRET, algorithms=["HS256"], options={"verify_exp": False})
        except jwt.InvalidTokenError:
            return {"valid": False, "reason": "bad_signature"}
        base = {"shipment_id": claims.get("sid"), "checkpoint_node": claims.get("cp")}
        if claims.get("exp", 0) < self.clock.event_ts().timestamp():
            return {"valid": False, "reason": "expired", **base}
        p = self.passes.get(claims.get("pid"))
        if p is None:
            return {"valid": False, "reason": "pass_not_found", **base}
        if p["status"] != "active":
            return {"valid": False, "reason": f"pass_{p['status']}", **base}
        broken = verify_chain(self.ledger)
        block = next((b for b in self.ledger if b["hash"] == claims["block_hash"]), None)
        if block is None or (broken is not None and block["index"] >= broken):
            return {"valid": False, "reason": "ledger_record_changed", **base}
        if block["doc_hash"] != claims["doc_hash"]:
            return {"valid": False, "reason": "doc_hash_mismatch", **base}
        return {"valid": True, "reason": None, **base}

    # ---------------- пропуска и реестр ----------------

    def _sign(self, pid, sid, cp, dhash, bhash, valid_until) -> str:
        return jwt.encode({"pid": pid, "sid": sid, "cp": cp, "doc_hash": dhash, "block_hash": bhash,
                           "exp": int(parse(valid_until).timestamp())}, PASS_SECRET, algorithm="HS256")

    def _new_pass_id(self, sid: str) -> str:
        n = sid[3:]
        if f"pass-{n}" not in self.passes:
            return f"pass-{n}"
        k = sum(1 for p in self.passes if p.startswith(f"pass-{n}-r")) + 1
        return f"pass-{n}-r{k}"

    def issue_pass(self, sid: str, checkpoint: str, event: str, dhash: str, ts: str):
        """Новый пропуск и блок реестра. Сбой — до любых изменений (ни блока, ни пропуска)."""
        if self.fail_next_pass > 0:
            self.fail_next_pass -= 1
            raise PassIssueError("сервис выпуска пропусков недоступен")
        block = append_block(self.ledger, ts, event, sid, checkpoint, dhash)
        pid = self._new_pass_id(sid)
        valid_until = self.meta["pass_valid_until"]
        p = {"id": pid, "shipment_id": sid, "checkpoint_node": checkpoint,
             "token": self._sign(pid, sid, checkpoint, dhash, block["hash"], valid_until),
             "doc_hash": dhash, "block_hash": block["hash"], "valid_until": valid_until, "status": "active"}
        self.passes[pid] = p
        self.emit("ledger.appended", block)
        return p, block

    def tamper(self, index: int) -> None:
        if not 0 <= index < len(self.ledger):
            raise ApiError(404, "block_not_found", f"Блока {index} нет")
        self.ledger[index]["doc_hash"] = "0" * 64  # «подделка документа»

    def arm_pass_failure(self, count: int = 1) -> None:
        self.fail_next_pass += count

    # ---------------- документы ----------------

    def _checks(self, fields: dict, sh: dict) -> list[dict]:
        missing = [f for f in REQUIRED_FIELDS if fields.get(f) in (None, "")]
        checks = [{"name": "required_fields", "ok": not missing,
                   "note": "Все обязательные поля заполнены" if not missing
                   else "Не заполнено: " + ", ".join(missing)}]
        kg, want = fields.get("weight_kg"), sh["weight_t"] * 1000
        if kg:
            ok = abs(kg - want) <= WEIGHT_TOLERANCE * want
            kgs = f"{kg:,.0f}".replace(",", " ")
            note = (f"Вес {kgs} кг совпадает с заявкой ({sh['weight_t']:g} т)" if ok
                    else f"Вес {kgs} кг расходится с заявкой ({sh['weight_t']:g} т) больше чем на 5%")
            checks.append({"name": "weight_match", "ok": ok, "note": note})
        hs = fields.get("hs_code") or ""
        checks.append({"name": "hs_code", "ok": bool(HS_RE.match(hs)),
                       "note": f"Код ТН ВЭД {hs}" if HS_RE.match(hs) else f"Проверьте код ТН ВЭД «{hs}»"})
        return checks

    def upload_document(self, sid: str) -> dict:
        sh = self.get_shipment(sid)
        did = f"doc-{sid[3:]}"
        if self.documents.get(did, {}).get("status") == "confirmed":
            raise ApiError(409, "document_confirmed", f"Документ {did} уже подтверждён")
        # распознавание: vision-LLM позже; запасной путь — закэшированный результат демо-инвойса
        cached = self.demo_drafts.get(sid) or next(iter(self.demo_drafts.values()))
        doc = copy.deepcopy(cached)
        doc.update(id=did, shipment_id=sid, status="draft", hash=None)
        doc["checks"] = self._checks(doc["fields"], sh)
        self.documents[did] = doc
        return copy.deepcopy(doc)

    def confirm_document(self, doc_id: str, fields: dict) -> dict:
        doc = self.documents.get(doc_id)
        if doc is None:
            raise ApiError(404, "document_not_found", f"Документ {doc_id} не найден")
        if doc["status"] == "confirmed":
            raise ApiError(409, "document_confirmed", f"Документ {doc_id} уже подтверждён")
        sh = self.get_shipment(doc["shipment_id"])
        fields = normalize_fields(fields)
        checks = self._checks(fields, sh)
        bad = [c["note"] for c in checks if not c["ok"] and c["name"] != "hs_code"]
        if bad:
            raise ApiError(422, "document_invalid", "; ".join(bad))
        h = doc_hash(fields)
        try:
            p, block = self.issue_pass(sh["id"], D.checkpoint_of(self, sh["route"]), "issued", h,
                                       self._event_iso())
        except PassIssueError:
            raise ApiError(503, "pass_issue_failed", "Пропуск не выпущен, повторите подтверждение")
        doc.update(fields=fields, checks=checks, status="confirmed", hash=h)
        sh["pass_id"], sh["pass_state"] = p["id"], "active"
        self.emit("shipment.updated", sh)
        return {"document": copy.deepcopy(doc), "pass": copy.deepcopy(p), "block": copy.deepcopy(block)}

    def _event_iso(self) -> str:
        return iso(self.clock.event_ts())

    # ---------------- действия под блокировкой ----------------

    async def run_scenario(self, preset: str):
        async with self.lock:
            return D.run_scenario(self, preset)

    async def accept(self, alert_id: str, via: str):
        async with self.lock:
            return D.accept(self, alert_id, via)

    async def reject(self, alert_id: str):
        async with self.lock:
            a = self.alerts.get(alert_id)
            if a is None:
                raise ApiError(404, "alert_not_found", f"Алерт {alert_id} не найден")
            if a["status"] == "accepted":
                raise ApiError(409, "already_accepted", "Алерт уже принят")
            if a["status"] == "new":
                a["status"] = "rejected"
                self.emit("alert.updated", a)
            return copy.deepcopy(a)

    async def retry_pass(self, sid: str):
        async with self.lock:
            return D.retry_pass(self, sid)

    async def reroute(self, sid: str, route_id: str):
        async with self.lock:
            return D.reroute(self, sid, route_id)

    async def create_shipment(self, body: dict):
        async with self.lock:
            return D.plan_new_shipment(self, body)

    async def confirm(self, doc_id: str, fields: dict):
        async with self.lock:
            return self.confirm_document(doc_id, fields)

    def link_user(self, telegram_id: int, name: str) -> None:
        self.users[telegram_id] = name


state = State()
