"""Состояние сервера. Пока — мок-режим: ответы берутся из data/mock/*.json по «фазе» демо.

Фазы: initial (шторм не запущен) → storm (после POST /scenarios) → accepted (после accept).
POST /demo/reset возвращает initial. Логики диспетчера здесь нет — только выбор файла.
TODO: заменить на настоящее in-memory состояние из data/seed.json.
"""
import asyncio
import copy
import json
from functools import lru_cache

import jwt

from .config import MOCK_DIR, MOCK_JWT_SECRET
from .ledger import verify_chain

AFFECTED = ("sh-01", "sh-02", "sh-03")


@lru_cache(maxsize=None)
def _load(name: str):
    return json.loads((MOCK_DIR / f"{name}.json").read_text(encoding="utf-8"))


def mock(name: str):
    return copy.deepcopy(_load(name))


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


class MockState:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.reset()

    def reset(self):
        self.phase = "initial"
        self.doc_confirmed = False
        self.alert_rejected = False
        self.accepted_via = "web"
        self.tampered: int | None = None

    def _pick(self, name: str, phases=("storm", "accepted")):
        if self.phase == "accepted" and "accepted" in phases:
            return mock(f"{name}.accepted")
        if self.phase in ("storm", "accepted") and "storm" in phases:
            return mock(f"{name}.storm")
        return mock(name)

    # ---------- чтение ----------
    def graph(self):
        return mock("graph")

    def shipments(self, owner_tg_id: int | None = None):
        items = self._pick("shipments")
        if self.doc_confirmed and self.phase != "accepted":
            for s in items:
                if s["id"] == "sh-05":
                    s["pass_id"], s["pass_state"] = "pass-05", "active"
        if owner_tg_id is not None:
            items = [s for s in items if s["owner_tg_id"] == owner_tg_id]
        return items

    def shipment(self, sid: str):
        for s in self.shipments():
            if s["id"] == sid:
                return s
        raise ApiError(404, "shipment_not_found", f"Груз {sid} не найден")

    def alternatives(self, sid: str):
        self.shipment(sid)
        return self._pick("alternatives")[sid]

    def weather(self):
        return self._pick("weather", phases=("storm",))

    def sailings(self, from_: str | None, to: str | None):
        items = self._pick("sailings", phases=("accepted",))
        return [s for s in items if (not from_ or s["from"] == from_) and (not to or s["to"] == to)]

    def alerts(self, status: str | None = None):
        if self.phase == "initial":
            items = []
        elif self.phase == "storm":
            items = mock("alerts.storm")
            if self.alert_rejected:
                items[0]["status"] = "rejected"
        else:
            items = mock("alerts.accepted")
            items[0]["accepted_via"] = self.accepted_via
        return [a for a in items if not status or a["status"] == status]

    def stats(self):
        return self._pick("stats")

    def ledger(self):
        chain = mock("ledger.accepted")
        n = 8 if self.phase == "accepted" else 5 if self.doc_confirmed else 4
        chain = chain[:n]
        if self.tampered is not None and self.tampered < n:
            chain[self.tampered]["doc_hash"] = "0" * 64  # «подделка документа»
        return chain

    def ledger_verify(self):
        broken = verify_chain(self.ledger())
        return {"valid": broken is None, "broken_at": broken}

    def passes(self):
        if self.phase == "accepted":
            return mock("passes.accepted")
        items = mock("passes")
        if self.doc_confirmed:
            items += [p for p in mock("passes.accepted") if p["id"] == "pass-05"]
        return items

    def pass_(self, pid: str):
        for p in self.passes():
            if p["id"] == pid:
                return p
        raise ApiError(404, "pass_not_found", f"Пропуск {pid} не найден")

    def verify_pass(self, token: str):
        try:
            claims = jwt.decode(token, MOCK_JWT_SECRET, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return {"valid": False, "reason": "expired"}
        except jwt.InvalidTokenError:
            return {"valid": False, "reason": "bad_signature"}
        base = {"shipment_id": claims["sid"], "checkpoint_node": claims["cp"]}
        try:
            p = self.pass_(claims["pid"])
        except ApiError:
            return {"valid": False, "reason": "pass_not_found", **base}
        if p["status"] != "active":
            return {"valid": False, "reason": f"pass_{p['status']}", **base}
        chain = self.ledger()
        broken = verify_chain(chain)
        block = next((b for b in chain if b["hash"] == claims["block_hash"]), None)
        if block is None or (broken is not None and block["index"] >= broken):
            return {"valid": False, "reason": "ledger_record_changed", **base}
        if block["doc_hash"] != claims["doc_hash"]:
            return {"valid": False, "reason": "doc_hash_mismatch", **base}
        return {"valid": True, "reason": None, **base}

    # ---------- действия ----------
    def run_scenario(self, preset: str):
        if preset != "storm_north":
            raise ApiError(501, "not_in_mock", "В моках есть только сценарий storm_north")
        if self.phase == "initial":
            self.phase = "storm"
        out = mock("scenario_storm_north")
        out["alert"] = self.alerts()[0]
        return out

    def _accept_result(self, already: bool):
        alert = self.alerts()[0]
        decision = mock("decision")
        decision["accepted_via"] = self.accepted_via
        return {"alert": alert,
                "shipments": [s for s in self.shipments() if s["id"] in AFFECTED],
                "blocks": self.ledger()[5:8], "decision": decision, "already_accepted": already}

    async def accept(self, alert_id: str, via: str):
        async with self.lock:
            if self.phase == "initial" or alert_id != "alert-001":
                raise ApiError(404, "alert_not_found", f"Алерт {alert_id} не найден")
            if self.phase == "accepted":
                return self._accept_result(already=True)
            if self.alert_rejected:
                raise ApiError(409, "alert_rejected", "Алерт уже отклонён")
            self.phase = "accepted"
            self.accepted_via = via
            self.doc_confirmed = True  # в моках порядок фиксирован: инвойс №05 → шторм → принятие
            return self._accept_result(already=False)

    def reject(self, alert_id: str):
        if self.phase == "initial" or alert_id != "alert-001":
            raise ApiError(404, "alert_not_found", f"Алерт {alert_id} не найден")
        if self.phase == "accepted":
            raise ApiError(409, "already_accepted", "Алерт уже принят")
        self.alert_rejected = True
        return self.alerts()[0]

    def confirm_document(self, doc_id: str):
        if doc_id != "doc-05":
            raise ApiError(404, "document_not_found", f"Черновик {doc_id} не найден (в моках — doc-05)")
        self.doc_confirmed = True
        return mock("document_confirm")

    def tamper(self, index: int):
        if not 0 <= index < len(self.ledger()):
            raise ApiError(404, "block_not_found", f"Блока {index} нет")
        self.tampered = index


state = MockState()
