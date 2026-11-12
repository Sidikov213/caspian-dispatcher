"""storm_north: числа сценария, одновременный accept, сбой пропуска, воспроизводимость после reset."""
import asyncio
import json

import gen_mocks as ref  # независимый расчёт по формулам DEMO_SCENARIO (scripts/gen_mocks.py)
import pytest

from app.errors import ApiError

AFFECTED = ("sh-01", "sh-02", "sh-03")
FERRY_A, FERRY_B, FERRY_M = ref.FERRY_A, ref.FERRY_B, ref.FERRY_M


def storm(st):
    out = asyncio.run(st.run_scenario("storm_north"))
    return out["alert"]


EXPECTED_TEXT = (  # тексты из DEMO_SCENARIO.md, раздел «Тексты, которые из этого следуют»
    "⚠️ Шторм на Северном Каспии: 14 ноя 02:00–21:00, волна до 3,4 м (предел парома 2,5 м).\n"
    "Под риском паром А Астрахань → Энзели (14 ноя, 10:00): 3 груза, 120 т.\n"
    "Риск срыва стыковки до 82%: отправление на 18 ч позже планового рейса.\n\n"
    "Ничего не делать: если рейс А отменят, ждать рейс Б — прибытие +48 ч, "
    "задержка обойдётся в 720 тыс ₽ по трём грузам.\n"
    "Через Махачкалу (паром М, 15 ноя, 06:00): прибытие +6 ч к плану, 123 тыс ₽.\n\n"
    "Расчётная экономия по 3 грузам: 126 груз-часов, 597 тыс ₽, −1,8 т CO₂ (−6,9%)."
)


# ---------------- тест 1: числа сценария ----------------

def test_seventeen_numbers_match_gen_mocks(st):
    got = ref.engine_numbers(st, storm(st))
    want = ref.reference_numbers()
    assert len(got) == len(ref.SCENARIO_DOC) == 17
    for name, doc in ref.SCENARIO_DOC.items():
        assert got[name] == pytest.approx(want[name]), name
        assert got[name] == pytest.approx(doc), name


def test_risk_and_two_step_forecast(st):
    alert = storm(st)
    for sid, p in zip(AFFECTED, (0.82, 0.74, 0.68)):
        r = st.shipments[sid]["risk"]
        assert r["miss_probability"] == p
        assert r["level"] == "high"
        assert r["departure_shift_h"] == 18           # отправление на 18 ч позже планового рейса
        assert r["arrival_delay_h"] == 48             # если рейс А отменят — ждать рейс Б
        assert [f["impact_hours"] for f in r["factors"]] == [11, 5, 2]
        assert st.shipments[sid]["display_status"] == "at_risk"
    assert {i["sailing_id"] for i in alert["items"]} == {FERRY_M}
    assert alert["port_load"] == {"node_id": "makhachkala", "before": 0.55, "after": 0.61}
    assert alert["text"] == EXPECTED_TEXT


def test_routes_match_reference_timeline(st):
    alert = storm(st)
    keys = ("edge_id", "sailing_id", "planned_start", "planned_end")
    for it in alert["items"]:
        want = ref.ROUTES[it["shipment_id"]]["mkh"]
        got = it["to_route"]
        assert [tuple(leg[k] for k in keys) for leg in got["legs"]] == \
               [tuple(leg[k] for k in keys) for leg in want["legs"]]
        assert got["id"] == want["id"]
        assert (got["total_cost_rub"], got["total_co2_kg"]) == (want["total_cost_rub"], want["total_co2_kg"])


def test_alternatives_include_west_and_wait(st):
    storm(st)
    alts = st.alternatives("sh-01")
    assert [a["route"]["id"] for a in alts] == ["r-sh-01-mkh", "r-sh-01-plan", "r-sh-01-west"]
    assert [a["recommended"] for a in alts] == [True, False, False]
    assert [a["delta"]["hours"] for a in alts] == [6, 48, 13]


def test_accept_applies_everything(client):
    client.post("/api/scenarios", json={"preset": "storm_north"}).raise_for_status()
    r = client.post("/api/alerts/alert-001/accept", json={"via": "telegram"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["already_accepted"] is False
    assert out["alert"]["status"] == "accepted" and out["alert"]["accepted_via"] == "telegram"
    assert [b["event"] for b in out["blocks"]] == ["reissued"] * 3
    assert {b["checkpoint_node"] for b in out["blocks"]} == {"makhachkala"}
    for s in out["shipments"]:
        assert s["display_status"] == "rerouted" and s["route"]["id"].endswith("-mkh")
        assert s["pass_id"].endswith("-r1") and s["pass_state"] == "active"
    stats = client.get("/api/stats").json()
    assert stats == {"saved_hours": 126, "saved_rub": 596640, "co2_saved_kg": 1824, "decisions": 1,
                     "shipments_total": 5, "at_risk": 0}
    sail = {s["id"]: s for s in client.get("/api/sailings").json()}
    assert sail[FERRY_M]["booked_t"] == 760 + 120 and sail[FERRY_A]["booked_t"] == 1310 - 120
    passes = {p: client.get(f"/api/passes/{p}").json() for p in ("pass-01", "pass-01-r1")}
    assert passes["pass-01"]["status"] == "reissued" and passes["pass-01-r1"]["status"] == "active"
    assert client.post("/api/passes/verify", json={"token": passes["pass-01-r1"]["token"]}).json()["valid"]
    assert not client.post("/api/passes/verify", json={"token": passes["pass-01"]["token"]}).json()["valid"]
    assert client.get("/api/ledger/verify").json() == {"valid": True, "broken_at": None}


# ---------------- тест 2: одновременный accept ----------------

def test_concurrent_accept_creates_one_decision(st):
    storm(st)

    async def both():
        return await asyncio.gather(st.accept("alert-001", "web"), st.accept("alert-001", "telegram"))

    a, b = asyncio.run(both())
    assert sorted([a["already_accepted"], b["already_accepted"]]) == [False, True]
    assert a["decision"] == b["decision"]
    assert len(st.decisions) == 1
    assert st.sailings[FERRY_M]["booked_t"] == 760 + 120          # один резерв
    assert len([p for p in st.passes if p.endswith("-r1")]) == 3
    assert len(st.ledger) == 4 + 3
    assert st.stats()["saved_rub"] == 596640


def test_repeat_accept_over_http_returns_same(client):
    client.post("/api/scenarios", json={"preset": "storm_north"})
    first = client.post("/api/alerts/alert-001/accept", json={"via": "web"}).json()
    again = client.post("/api/alerts/alert-001/accept", json={"via": "telegram"}).json()
    assert again["already_accepted"] is True
    assert again["decision"] == first["decision"] and again["alert"] == first["alert"]
    assert client.get("/api/stats").json()["decisions"] == 1


# ---------------- тест 3: сбой выпуска пропуска и повтор ----------------

def test_pass_failure_then_retry_is_idempotent(client):
    client.post("/api/scenarios", json={"preset": "storm_north"})
    assert client.post("/api/demo/fail_next_pass").json() == {"ok": True}
    out = client.post("/api/alerts/alert-001/accept", json={"via": "web"}).json()
    sh = {s["id"]: s for s in out["shipments"]}
    assert sh["sh-01"]["pass_state"] == "reissue_pending" and sh["sh-01"]["pass_id"] == "pass-01"
    assert sh["sh-01"]["route"]["id"] == "r-sh-01-mkh"           # маршрут уже сменён
    assert client.get("/api/passes/pass-01").json()["status"] == "active"   # старый пропуск действует
    assert [b["shipment_id"] for b in out["blocks"]] == ["sh-02", "sh-03"]
    assert client.get("/api/stats").json()["saved_rub"] == 596640

    r1 = client.post("/api/shipments/sh-01/pass/retry")
    assert r1.status_code == 200, r1.text
    r1 = r1.json()
    assert r1["pass"]["id"] == "pass-01-r1" and r1["shipment"]["pass_state"] == "active"
    assert client.get("/api/passes/pass-01").json()["status"] == "reissued"
    r2 = client.post("/api/shipments/sh-01/pass/retry").json()  # повтор ничего нового не выпускает
    assert r2["pass"] == r1["pass"]

    ledger = client.get("/api/ledger").json()
    assert len(ledger) == 4 + 3 and [b["shipment_id"] for b in ledger[4:]] == ["sh-02", "sh-03", "sh-01"]
    assert client.get("/api/stats").json() == {"saved_hours": 126, "saved_rub": 596640, "co2_saved_kg": 1824,
                                               "decisions": 1, "shipments_total": 5, "at_risk": 0}
    for n in ("01", "02", "03"):
        assert client.get(f"/api/passes/pass-{n}-r1").status_code == 200
        assert client.get(f"/api/passes/pass-{n}-r2").status_code == 404


def test_retry_fails_again_visibly(st):
    storm(st)
    st.arm_pass_failure()
    asyncio.run(st.accept("alert-001", "web"))
    st.arm_pass_failure()
    with pytest.raises(ApiError) as e:
        asyncio.run(st.retry_pass("sh-01"))
    assert e.value.status == 503
    assert st.shipments["sh-01"]["pass_state"] == "reissue_pending"
    assert st.passes["pass-01"]["status"] == "active"
    assert asyncio.run(st.retry_pass("sh-01"))["pass"]["id"] == "pass-01-r1"
    assert len(st.decisions) == 1


# ---------------- тест 6: reset даёт идентичный повторный прогон ----------------

def full_run(client) -> str:
    calls = [
        ("get", "/api/shipments", None), ("get", "/api/stats", None), ("get", "/api/ledger", None),
        ("post", "/api/scenarios", {"preset": "storm_north"}),
        ("get", "/api/shipments/sh-01/alternatives", None), ("get", "/api/weather", None),
        ("post", "/api/demo/fail_next_pass", None),
        ("post", "/api/alerts/alert-001/accept", {"via": "web"}),
        ("post", "/api/shipments/sh-01/pass/retry", None),
        ("get", "/api/shipments", None), ("get", "/api/alerts", None), ("get", "/api/sailings", None),
        ("get", "/api/ledger", None), ("get", "/api/stats", None), ("get", "/api/passes/pass-01-r1", None),
    ]
    out = []
    for method, url, body in calls:
        r = getattr(client, method)(url, json=body) if body is not None else getattr(client, method)(url)
        assert r.status_code == 200, (url, r.text)
        out.append(r.text)
    return "\n".join(out)


def test_reset_gives_identical_rerun(client):
    first = full_run(client)
    assert client.post("/api/demo/reset").json() == {"ok": True}
    assert client.get("/api/alerts").json() == []
    assert client.get("/api/stats").json()["decisions"] == 0
    second = full_run(client)
    assert first == second                              # байт в байт при фиксированных часах


def test_live_clock_rerun_same_numbers():
    """Живые часы: метки событий идут, числа и маршруты повторяются."""
    from app.state import State
    st = State()

    def run():
        a = asyncio.run(st.run_scenario("storm_north"))["alert"]
        out = asyncio.run(st.accept(a["id"], "web"))
        return (json.dumps(a["totals"]), [s["route"]["id"] for s in out["shipments"]], st.stats())

    first = run()
    st.reset()
    assert run() == first


def test_mock_files_match_engine(client):
    """Фронтенд, читающий data/mock/ напрямую, видит те же числа, что отдаёт сервер."""
    from app.config import MOCK_DIR
    for url, name in (("/api/shipments", "shipments"), ("/api/stats", "stats"), ("/api/sailings", "sailings"),
                      ("/api/ledger", "ledger"), ("/api/graph", "graph"), ("/api/weather", "weather")):
        mock = json.loads((MOCK_DIR / f"{name}.json").read_text(encoding="utf-8"))
        assert client.get(url).json() == mock, name
    mock_alts = json.loads((MOCK_DIR / "alternatives.json").read_text(encoding="utf-8"))
    assert client.get("/api/shipments/sh-01/alternatives").json() == mock_alts["sh-01"]
