/* Пульт диспетчера — Telegram Mini App. Чистый JS без сборки.
 * Вход: Telegram initData → POST /api/tg/auth → сессионный токен (Authorization: Bearer, /ws?token=).
 * Данные только из API; клиент ничего не считает, только форматирует (CLAUDE.md, раздел 9).
 * Обновление: WebSocket /ws, при обрыве — опрос /shipments, /alerts, /stats раз в 3 с. */
(function () {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp;
  const $ = (sel) => document.querySelector(sel);
  const NBSP = " ";
  const MINUS = "−";
  const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

  // Словарь интерфейса (CLAUDE.md, раздел 9): подписи, а не данные.
  const STATUS = {
    planned: "Запланирован ⚪", in_transit: "В пути 🔵", at_risk: "Под риском 🔴",
    rerouted: "Перестроен 🟢", delivered: "Доставлен ✅",
  };
  const LEVEL = { low: "низкий", medium: "средний", high: "высокий" };
  const CARGO = { grain: "Зерно", metal: "Металл", equipment: "Оборудование", textile: "Текстиль", fertilizer: "Удобрения" };
  const BLOCK_EVENT = { issued: "Пропуск выдан", reissued: "Пропуск переоформлен", verified: "Пропуск проверен" };
  const PASS_STATUS = { active: "действует", reissued: "переоформлен", revoked: "отозван" };
  const VIA = { web: "с сайта", telegram: "из Telegram" };
  const MODE_ICON = { rail: "i-rail", sea: "i-sea", road: "i-road" };
  const POLL_MS = 3000;

  const S = {
    token: null, company: "", nodes: {}, nodeList: [], shipments: [], alerts: [], stats: null, weather: null,
    ledger: [], verify: null, passes: {}, alts: {}, selectedOption: null, showOptions: false, busy: false,
    ws: null, pollTimer: null, wsRetry: null, cargoTypes: [],
  };

  // ---------- формат ----------
  const num = (x, d = 0) => {
    const s = Math.abs(x).toFixed(d).replace(".", ",");
    const [i, f] = s.split(",");
    return (x < 0 ? MINUS : "") + i.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP) + (f ? "," + f : "");
  };
  const dec = (x) => num(x, Number.isInteger(x) ? 0 : 1);
  const hrs = (x) => (x > 0 ? "+" : "") + dec(x) + NBSP + "ч";
  const pct = (p) => Math.round(p * 100) + "%";
  const rub = (x) => {
    const a = Math.abs(x);
    if (a >= 1e6) return num(x / 1e6, 1) + NBSP + "млн" + NBSP + "₽";
    if (a >= 1e3) return num(Math.round(x / 1e3)) + NBSP + "тыс" + NBSP + "₽";
    return num(Math.round(x)) + NBSP + "₽";
  };
  const co2pct = (p) => (p > 0 ? "+" : "") + dec(p) + "%" + NBSP + "CO₂";
  const msk = (iso) => new Date(new Date(iso).getTime() + 3 * 3600e3);
  const when = (iso) => {
    const d = msk(iso);
    return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}, ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
  };
  const clock = (iso) => when(iso).split(", ")[1];
  const shortName = (id) => {
    const n = S.nodes[id];
    return n ? n.name.replace(/\s*\(.*\)\s*$/, "").replace(/\s*\/.*$/, "") : id;
  };
  const shipNo = (id) => (/^sh-(\d+)$/.test(id) ? "№" + id.slice(3) : id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const chip = (status) => `<span class="chip ${status}"><i></i>${esc(STATUS[status] || status)}</span>`;
  const icon = (id) => `<svg><use href="#${id}"/></svg>`;

  // ---------- сеть ----------
  async function api(path, opts = {}, retry = true) {
    const res = await fetch("/api" + path, {
      ...opts,
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + S.token, ...(opts.headers || {}) },
    });
    if (res.status === 401 && retry && path !== "/tg/auth") {
      await auth();
      return api(path, opts, false);
    }
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      const e = new Error((body && body.error && body.error.message) || res.statusText);
      e.status = res.status;
      e.code = body && body.error && body.error.code;
      throw e;
    }
    return body;
  }

  async function auth() {
    const res = await fetch("/api/tg/auth", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ init_data: tg.initData }),
    });
    const body = await res.json().catch(() => null);
    if (!res.ok) throw Object.assign(new Error((body && body.error && body.error.message) || "Вход не удался"), { status: res.status });
    S.token = body.token;
    S.company = body.company;
  }

  const upsert = (list, item) => {
    const i = list.findIndex((x) => x.id === item.id);
    if (i >= 0) list[i] = item; else list.push(item);
  };

  async function loadAll() {
    const [graph, shipments, alerts, stats, weather, ledger] = await Promise.all([
      api("/graph"), api("/shipments"), api("/alerts"), api("/stats"), api("/weather"), api("/ledger"),
    ]);
    S.nodes = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));
    S.nodeList = graph.nodes;
    Object.assign(S, { shipments, alerts, stats, weather, ledger });
    S.cargoTypes = [...new Set(shipments.map((s) => s.cargo_type))];
  }

  async function refreshLive() {
    const [shipments, alerts, stats] = await Promise.all([api("/shipments"), api("/alerts"), api("/stats")]);
    Object.assign(S, { shipments, alerts, stats });
    render();
  }

  function connectWs() {
    clearTimeout(S.wsRetry);
    const url = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws?token=" + encodeURIComponent(S.token);
    let ws;
    try { ws = new WebSocket(url); } catch (e) { startPolling(); return; }
    S.ws = ws;
    ws.onopen = () => { stopPolling(); setLive("on"); };
    ws.onclose = () => { setLive("poll"); startPolling(); S.wsRetry = setTimeout(connectWs, 10000); };
    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      const p = msg.payload;
      if (msg.type === "demo.reset") { resetAll(); return; }
      if (msg.type === "shipment.updated" && p) { upsert(S.shipments, p); delete S.alts[p.id]; }
      else if ((msg.type === "alert.created" || msg.type === "alert.updated") && p) upsert(S.alerts, p);
      else if (msg.type === "stats.updated" && p) S.stats = p;
      else if (msg.type === "ledger.appended" && p) { S.ledger.push(p); S.verify = null; }
      else if (msg.type === "weather.updated") api("/weather").then((w) => { S.weather = w; render(); }).catch(() => {});
      render();
    };
  }
  /** demo.reset: демо вернулось к началу — сбросить всё локальное и перезапросить с сервера. */
  function resetAll() {
    Object.assign(S, { alts: {}, passes: {}, verify: null, selectedOption: null, showOptions: false, busy: false });
    loadAll().then(render).catch(() => {});
  }
  const byWhom = (a) => a.accepted_by ? esc(a.accepted_by.name) + " " : "";
  function startPolling() {
    if (S.pollTimer) return;
    S.pollTimer = setInterval(() => refreshLive().catch(() => {}), POLL_MS);
  }
  function stopPolling() { clearInterval(S.pollTimer); S.pollTimer = null; }
  function setLive(mode) { const el = $("#live"); el.className = "live " + mode; el.title = mode === "on" ? "WebSocket" : "Опрос раз в 3 с"; }

  // ---------- маршрутизация ----------
  const route = () => {
    const h = location.hash.replace(/^#/, "") || "overview";
    const [name, arg] = h.split("/");
    return { name, arg };
  };
  const go = (hash) => { if (location.hash !== "#" + hash) location.hash = hash; else render(); };
  window.addEventListener("hashchange", () => { S.showOptions = false; render(); window.scrollTo(0, 0); });

  function toast(text) {
    const el = $("#toast");
    el.textContent = text;
    el.hidden = false;
    clearTimeout(toast.t);
    toast.t = setTimeout(() => (el.hidden = true), 3500);
  }

  // ---------- данные для экранов ----------
  const activeAlert = () => S.alerts.filter((a) => a.status === "new").sort((a, b) => b.created_at.localeCompare(a.created_at))[0] || null;
  const lastClosed = () => S.alerts.filter((a) => a.status === "superseded" && a.status_note === "угроза снята")
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0] || null;

  // ---------- экран: Решения ----------
  function viewDecisions() {
    const a = activeAlert();
    let html = "";
    if (a) {
      const opts = a.options || [];
      const rec = opts.find((o) => o.recommended) || null;
      if (!S.selectedOption || !opts.some((o) => o.id === S.selectedOption && o.id !== "wait")) S.selectedOption = rec && rec.id !== "wait" ? rec.id : null;
      const sel = opts.find((o) => o.id === S.selectedOption) || null;
      const others = opts.filter((o) => o.id !== (rec && rec.id));
      html += `<section class="card danger">
        <div class="row between"><p class="h">Активный алерт</p>${a.source ? `<span class="chip src">${a.source === "forecast" ? "По прогнозу" : "Сценарий"}</span>` : ""}</div>
        <p class="title">${esc(a.title)}</p>
        ${a.starts_in_h != null ? `<div class="sub">Угроза начнётся через ${dec(a.starts_in_h)}${NBSP}ч</div>` : ""}
        <div class="cols">
          <div class="col nothing"><div class="lbl">Ничего не делать</div><div class="big">${hrs(a.do_nothing.delay_hours)}</div>
            <div class="small">к плану · задержка ${rub(a.do_nothing.loss_rub)}</div></div>
          <div class="col solution"><div class="lbl">Решение диспетчера</div>
            ${sel ? `<div class="big">${hrs(sel.delay_vs_plan_h)}</div><div class="small">к плану · ${esc(sel.title)}</div>`
                  : `<div class="small">Обхода нет — лучший вариант ждать следующий рейс</div>`}</div>
        </div>
        ${sel ? `<div class="stat"><div class="small">Расчётная экономия</div>
          <div class="row" style="gap:16px;flex-wrap:wrap"><b class="big" style="font-size:28px">${rub(sel.saved_rub)}</b>
          <span>${dec(sel.saved_hours)}${NBSP}груз-часов</span></div></div>` : ""}
        ${opts.length ? `<div class="list">${(S.showOptions ? [rec, ...others] : [rec]).filter(Boolean).map((o) => optRow(o, a)).join("")}</div>` : ""}
        ${others.length ? `<button class="btn ghost" data-act="toggle-opts">${S.showOptions ? "Скрыть варианты" : "Другие варианты"}</button>` : ""}
        <button class="btn danger" data-act="reject" data-id="${a.id}">Отклонить</button>
        ${!tg.MainButton ? `<button class="btn primary" data-act="accept" data-id="${a.id}">Принять</button>` : ""}
        <div class="sep"></div>
        <p class="h">Грузы в алерте</p>
        <div class="list">${a.items.map((i) => alertItem(i)).join("")}</div>
      </section>`;
    } else {
      const closed = lastClosed();
      html += `<section class="card ${closed ? "ok" : ""}"><p class="h">Активный алерт</p>
        ${closed ? `<p class="title">✅ Угроза снята — решение не нужно</p><div class="sub">${esc(closed.title)}</div>`
                 : `<p class="title">Активных угроз нет</p><div class="sub">Наблюдатель проверяет прогноз на 48 часов вперёд</div>`}</section>`;
    }
    html += historyCard() + ledgerCard();
    return html;
  }

  function optRow(o, a) {
    const wait = o.id === "wait";
    const sel = S.selectedOption === o.id;
    return `<div class="opt ${sel ? "sel" : ""}" data-act="${wait ? "wait-info" : "pick"}" data-id="${o.id}">
      <span class="radio"></span>
      <div><div class="t">${esc(o.title)}${o.recommended ? `<span class="badge">рекомендуем</span>` : ""}</div>
      <div class="small">Прибытие ${hrs(o.delay_vs_plan_h)} к плану${wait ? " · это «Отклонить»" : ` · ${rub(o.saved_rub)} · ${dec(o.saved_hours)}${NBSP}груз-ч`}</div></div>
    </div>`;
  }

  function alertItem(i) {
    const sh = S.shipments.find((s) => s.id === i.shipment_id);
    if (!sh) return "";
    return `<div class="row between tap" data-go="shipment/${sh.id}">
      <div><b>${shipNo(sh.id)} ${esc(sh.title)}</b><div class="small">${i.action === "reroute" ? "обход, прибытие " + hrs(i.delay_vs_plan_h) + " к плану" : "ждать следующий рейс"}</div></div>
      <b class="lvl-${sh.risk.level}">${pct(sh.risk.miss_probability)}</b></div>`;
  }

  function historyCard() {
    const done = S.alerts.filter((a) => a.status === "accepted" || a.status === "rejected")
      .sort((a, b) => (b.accepted_at || b.created_at).localeCompare(a.accepted_at || a.created_at));
    const rows = done.map((a) => a.status === "accepted"
      ? `<div class="hist"><div><b>Принято</b> ${byWhom(a)}${a.accepted_via ? VIA[a.accepted_via] || "" : ""}<div class="small">${esc(a.title)}</div></div>
          <div style="text-align:right"><b>${rub(a.totals.saved_rub)}</b><div class="small">${a.accepted_at ? when(a.accepted_at) : ""}</div></div></div>`
      : `<div class="hist"><div><b>Отклонено</b><div class="small">${esc(a.title)}</div></div><div class="small">${when(a.created_at)}</div></div>`).join("");
    return `<section class="card"><p class="h">История решений</p>${rows || `<div class="sub">Решений пока нет</div>`}</section>`;
  }

  function ledgerCard() {
    const v = S.verify;
    const status = !v ? "" : v.valid ? `<div class="good"><b>Цепочка цела</b> · проверено ${S.ledger.length} записей</div>`
      : `<div class="bad"><b>Нарушение в записи №${v.broken_at}</b></div>`;
    const rows = S.ledger.slice(-8).reverse().map((b) => `<div class="block"><span class="ix">${String(b.index).padStart(2, "0")}</span>
      <div><b>${esc(BLOCK_EVENT[b.event] || b.event)}</b><div class="small">${shipNo(b.shipment_id)} · ${esc(shortName(b.checkpoint_node))} · ${when(b.ts)}</div></div>
      <span class="mono">${esc(b.hash.slice(0, 4))}…${esc(b.hash.slice(-4))}</span></div>`).join("");
    return `<section class="card"><div class="row between"><p class="h">Реестр пропусков</p></div>${status}
      ${rows || `<div class="sub">Записей пока нет</div>`}
      <button class="btn" data-act="verify">Проверить целостность</button></section>`;
  }

  // ---------- экран: Грузы ----------
  function viewShipments() {
    const rows = S.shipments.map((s) => `<div class="card tap ship" data-go="shipment/${s.id}">
      <div class="name"><span class="num">${shipNo(s.id)}</span>${esc(s.title)}</div>
      <div class="p lvl-${s.risk.level}">${pct(s.risk.miss_probability)}</div>
      <div class="route">${esc(shortName(s.origin))} → ${esc(shortName(s.destination))}</div>
      <div class="row" style="justify-content:flex-end;gap:6px">${s.manual ? `<span class="chip manual">создан вручную</span>` : ""}${chip(s.display_status)}</div>
    </div>`).join("");
    return `<button class="btn primary" data-go="new">+ Новый груз</button><div class="list">${rows || `<div class="empty">Грузов нет</div>`}</div>`;
  }

  function viewTwin(id) {
    const s = S.shipments.find((x) => x.id === id);
    if (!s) return `<div class="empty">Груз не найден</div>`;
    const r = s.risk;
    const C = 2 * Math.PI * 52;
    const ring = `<div class="ring"><svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="52" fill="none" stroke="#24304A" stroke-width="12"/>
      <circle cx="60" cy="60" r="52" fill="none" stroke="var(--${r.level})" stroke-width="12" stroke-linecap="round"
        stroke-dasharray="${(C * r.miss_probability).toFixed(1)} ${C.toFixed(1)}"/></svg><div class="val lvl-${r.level}">${pct(r.miss_probability)}</div></div>`;
    const maxF = Math.max(1, ...r.factors.map((f) => f.impact_hours));
    const factors = r.factors.map((f) => `<div><div class="row between"><span>${esc(f.label)}</span><b>${hrs(f.impact_hours)}</b></div>
      <div class="bar"><i style="width:${Math.max(4, (f.impact_hours / maxF) * 100)}%"></i></div></div>`).join("");
    const drivers = (r.probability_drivers || []).map((d) => `<div class="row between"><span>${esc(d.label)}</span>
      <b class="${d.impact_pp > 0 ? "bad" : "good"}">${d.impact_pp > 0 ? "+" : ""}${dec(d.impact_pp)}${NBSP}п.${NBSP}п.</b></div>`).join("");
    const legs = s.route.legs.map((l) => `<div class="leg ${l.status}">${icon(MODE_ICON[l.mode] || "i-road")}
      <div><b>${esc(shortName(l.from))} → ${esc(shortName(l.to))}</b><div class="small">${l.status === "blocked" ? "<span class='bad'>под угрозой</span>" : l.status === "active" ? "в пути" : l.status === "done" ? "пройден" : "впереди"}</div></div>
      <div class="when">${when(l.planned_end)}${l.predicted_delay_h > 0 ? `<div class="warn">${hrs(l.predicted_delay_h)}</div>` : ""}</div></div>`).join("");
    const p = s.pass_id ? S.passes[s.pass_id] : null;
    if (s.pass_id && !p) api("/passes/" + encodeURIComponent(s.pass_id)).then((x) => { S.passes[x.id] = x; render(); }).catch(() => {});
    const pass = !s.pass_id ? `<div class="sub">Пропуск не оформлен — нужен снимок инвойса в приложении экспедитора</div>`
      : s.pass_state === "reissue_pending" ? `<div class="warn"><b>Пропуск ожидает переоформления</b> — действует старый</div>
          <button class="btn" data-act="retry" data-id="${s.id}">Повторить</button>`
      : p ? `<div class="kv"><span>Пункт пропуска</span><span class="v">${esc(shortName(p.checkpoint_node))}</span>
          <span>Статус</span><span class="v">${esc(PASS_STATUS[p.status] || p.status)}</span>
          <span>Действует до</span><span class="v">${when(p.valid_until)}</span></div>` : `<div class="sub">Загрузка…</div>`;
    return `<section class="card">
        <div class="row between"><p class="title">${shipNo(s.id)} ${esc(s.title)}</p>${chip(s.display_status)}</div>
        <div class="sub">${esc(shortName(s.origin))} → ${esc(shortName(s.destination))} · ${dec(s.weight_t)}${NBSP}т${s.manual ? " · создан вручную" : ""}</div>
      </section>
      <section class="card"><p class="h">Риск срыва стыковки · ${LEVEL[r.level] || r.level}</p>
        <div class="ring-wrap">${ring}<div class="facts">
          ${r.departure_shift_h > 0 ? `<div class="fact"><b>${hrs(r.departure_shift_h)}</b><span class="sub">отправление на ${dec(r.departure_shift_h)}${NBSP}ч позже планового рейса</span></div>` : `<div class="sub">Отправление по расписанию</div>`}
          ${r.arrival_delay_h > 0 ? `<div class="fact"><b class="bad">${hrs(r.arrival_delay_h)}</b><span class="sub">если рейс отменят: прибытие ${hrs(r.arrival_delay_h)}</span></div>` : ""}
        </div></div>
        ${factors ? `<div class="sep"></div><p class="h">Причины</p>${factors}` : ""}
        ${drivers ? `<div class="sep"></div><p class="h">Что повлияло на вероятность</p>${drivers}` : ""}
      </section>
      <section class="card"><div class="row between"><p class="h">Этапы маршрута</p><span class="small">план · прогноз</span></div>
        <div class="legs">${legs}</div></section>
      <section class="card"><p class="h">CO₂ маршрута</p><div class="big">${num(Math.round(s.route.total_co2_kg))}${NBSP}<span style="font-size:18px">кг</span></div>
        ${S.alts[s.id] ? `<div class="sub">к плановому маршруту: ${S.alts[s.id].co2 > 0 ? "+" : ""}${num(Math.round(S.alts[s.id].co2))}${NBSP}кг</div>` : ""}</section>
      <section class="card"><p class="h">Пропуск</p>${pass}</section>`;
  }

  function loadAlt(id) {
    if (S.alts[id]) return;
    api("/shipments/" + encodeURIComponent(id) + "/alternatives").then((list) => {
      const cur = list.find((x) => x.route.id === (S.shipments.find((s) => s.id === id) || {}).route?.id);
      if (cur) { S.alts[id] = { co2: cur.delta.co2_kg }; render(); }
    }).catch(() => {});
  }

  // ---------- экран: Новый груз ----------
  function viewNew() {
    const nodes = S.nodeList.slice().sort((a, b) => a.name.localeCompare(b.name, "ru"));
    const opt = (n) => `<option value="${esc(n.id)}">${esc(n.name)}</option>`;
    const types = S.cargoTypes.map((t) => `<option value="${esc(t)}">${esc(CARGO[t] || t)}</option>`).join("");
    return `<section class="card"><p class="title">Новый груз</p>
      <form id="new-form" class="list" autocomplete="off">
        <div class="field"><label for="f-title">Название</label><input id="f-title" required maxlength="60" placeholder="Например, Зерно"></div>
        <div class="field"><label for="f-type">Тип груза</label><select id="f-type" required>${types}</select></div>
        <div class="field"><label for="f-weight">Вес, т</label><input id="f-weight" type="number" inputmode="decimal" min="1" step="1" required></div>
        <div class="field"><label for="f-from">Откуда</label><select id="f-from" required>${nodes.map(opt).join("")}</select></div>
        <div class="field"><label for="f-to">Куда</label><select id="f-to" required>${nodes.map(opt).join("")}</select></div>
        <div class="err" id="f-err" hidden></div>
        <button class="btn primary" type="submit">Создать груз</button>
      </form>
      <div class="small">Груз виден всем в демо-кабинете, участвует в сценариях и удаляется при сбросе демо.</div></section>`;
  }

  async function submitNew(ev) {
    ev.preventDefault();
    const err = $("#f-err");
    err.hidden = true;
    const body = {
      title: $("#f-title").value.trim(), cargo_type: $("#f-type").value, weight_t: Number($("#f-weight").value),
      origin: $("#f-from").value, destination: $("#f-to").value,
    };
    if (body.origin === body.destination) { err.textContent = "Откуда и куда совпадают"; err.hidden = false; return; }
    try {
      const sh = await api("/shipments", { method: "POST", body: JSON.stringify(body) });
      upsert(S.shipments, sh);
      haptic("success");
      go("shipment/" + sh.id);
    } catch (e) {
      err.textContent = e.code === "no_route" ? "Допустимого маршрута по расписанию нет" : e.message;
      err.hidden = false;
    }
  }

  // ---------- экран: Обзор ----------
  function viewOverview() {
    const a = activeAlert();
    const st = S.stats;
    const w = S.weather;
    let html = "";
    if (st) html += `<section class="card"><div class="grid2">
        <div class="stat"><div class="small">Под риском</div><div class="big xl ${st.at_risk ? "bad" : ""}">${st.at_risk}</div><div class="small">из ${st.shipments_total} грузов</div></div>
        <div class="stat"><div class="small">Решений принято</div><div class="big xl">${st.decisions}</div></div></div></section>`;
    html += a ? `<section class="card danger tap" data-go="decisions"><div class="row between"><p class="h">Активный алерт</p>${a.source ? `<span class="chip src">${a.source === "forecast" ? "По прогнозу" : "Сценарий"}</span>` : ""}</div>
        <p class="title">${esc(a.title)}</p>
        <div class="row" style="gap:16px"><div><div class="big bad">${hrs(a.do_nothing.delay_hours)}</div><div class="small">если ничего не делать</div></div>
        ${a.items.length ? `<div><div class="big">${a.items.length}</div><div class="small">груза под угрозой</div></div>` : ""}</div>
        <button class="btn primary" data-go="decisions">Открыть решение</button></section>`
      : `<section class="card"><p class="h">Активный алерт</p><div class="sub">Активных угроз нет</div></section>`;
    if (st) html += `<section class="card"><p class="h">Расчётная экономия</p>
        <div class="big">${rub(st.saved_rub)}</div>
        <div class="row" style="gap:16px;flex-wrap:wrap"><span><b>${dec(st.saved_hours)}</b> груз-часов</span>
        ${st.co2_saved_pct != null && st.co2_saved_pct !== 0 ? `<span class="good"><b>${co2pct(-st.co2_saved_pct)}</b></span>` : ""}</div></section>`;
    if (w) {
      const age = Math.max(0, Math.round((Date.now() - new Date(w.updated_at).getTime()) / 60000));
      const stale = w.stale || age > 60;
      html += `<section class="card"><div class="row between"><p class="h">Волна в портах</p>${icon("i-wave")}</div>
        <div class="kv">${w.points.map((p) => `<span>${esc(shortName(p.node_id))}</span><span class="v">${dec(p.wave_height_m)}${NBSP}м · ветер ${dec(p.wind_ms)}${NBSP}м/с</span>`).join("")}</div>
        <div class="${stale ? "warn" : "small"}">Погода обновлена ${age < 1 ? "только что" : age + " мин назад"}${stale ? " · данные устарели" : ""}</div></section>`;
    }
    return html + `<div class="footer">Расписание и загрузка портов — демо-данные</div>`;
  }

  // ---------- отрисовка ----------
  function render() {
    const r = route();
    const tab = ["shipment", "new"].includes(r.name) ? "shipments" : (["overview", "shipments", "decisions"].includes(r.name) ? r.name : "overview");
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
    $("#tab-dot").hidden = !activeAlert();
    $("#company").textContent = S.company ? `Демо-кабинет компании „${S.company}“` : "";
    const view = $("#view");
    if (r.name === "decisions") view.innerHTML = viewDecisions();
    else if (r.name === "shipments") view.innerHTML = viewShipments();
    else if (r.name === "shipment") { view.innerHTML = viewTwin(r.arg); loadAlt(r.arg); }
    else if (r.name === "new") { if (!view.querySelector("#new-form")) { view.innerHTML = viewNew(); $("#new-form").addEventListener("submit", submitNew); } }
    else view.innerHTML = viewOverview();
    syncTelegramButtons(r);
  }

  function syncTelegramButtons(r) {
    if (!tg) return;
    if (["shipment", "new"].includes(r.name)) tg.BackButton.show(); else tg.BackButton.hide();
    const a = activeAlert();
    const mb = tg.MainButton;
    if (r.name === "decisions" && a && S.selectedOption) {
      const o = (a.options || []).find((x) => x.id === S.selectedOption);
      mb.setParams({ text: o && !o.recommended ? "Принять: " + o.title.replace(/\s*\(.*\)\s*$/, "") : "Принять", color: "#2F80ED", text_color: "#FFFFFF" });
      mb.show();
      S.busy ? mb.showProgress() : mb.hideProgress();
    } else {
      mb.hide();
    }
  }

  function haptic(kind) { try { tg.HapticFeedback.notificationOccurred(kind); } catch (e) { /* вне Telegram */ } }

  // ---------- действия ----------
  async function accept() {
    const a = activeAlert();
    if (!a || S.busy) return;
    S.busy = true; render();
    try {
      const body = { via: "telegram" };
      const o = (a.options || []).find((x) => x.id === S.selectedOption);
      if (o && !o.recommended) body.option_id = o.id;
      const res = await api(`/alerts/${encodeURIComponent(a.id)}/accept`, { method: "POST", body: JSON.stringify(body) });
      upsert(S.alerts, res.alert);
      res.shipments.forEach((s) => upsert(S.shipments, s));
      haptic("success");
      toast(res.already_accepted
        ? `Уже принято в ${clock(res.alert.accepted_at)} ${VIA[res.alert.accepted_via] || ""}`
        : `Принято. Расчётная экономия ${rub(res.alert.totals.saved_rub)}`);
    } catch (e) {
      haptic("error");
      if (e.code === "superseded") toast("Предложение устарело — показываем актуальное");
      else if (e.code === "alert_rejected") toast("Предложение уже отклонено");
      else toast(e.message);
    } finally {
      S.busy = false;
      await refreshLive().catch(() => {});
    }
  }

  async function reject(id) {
    const ok = await new Promise((resolve) => (tg && tg.showConfirm ? tg.showConfirm("Отклонить предложение? Груз ждёт следующий рейс.", resolve) : resolve(confirm("Отклонить?"))));
    if (!ok) return;
    try {
      upsert(S.alerts, await api(`/alerts/${encodeURIComponent(id)}/reject`, { method: "POST" }));
      toast("Отклонено: груз ждёт следующий рейс");
    } catch (e) {
      toast(e.code === "already_accepted" ? "Уже принято" : e.message);
    }
    refreshLive().catch(() => {});
  }

  document.addEventListener("click", async (ev) => {
    const t = ev.target.closest("[data-go],[data-act],.tab");
    if (!t) return;
    if (t.classList.contains("tab")) return go(t.dataset.tab);
    if (t.dataset.go) return go(t.dataset.go);
    const act = t.dataset.act;
    if (act === "toggle-opts") { S.showOptions = !S.showOptions; render(); }
    else if (act === "pick") { S.selectedOption = t.dataset.id; render(); }
    else if (act === "wait-info") toast("«Ждать следующий рейс» — это «Отклонить»");
    else if (act === "accept") accept();
    else if (act === "reject") reject(t.dataset.id);
    else if (act === "verify") {
      try { S.verify = await api("/ledger/verify"); S.ledger = await api("/ledger"); render(); } catch (e) { toast(e.message); }
    } else if (act === "retry") {
      try { const r = await api(`/shipments/${encodeURIComponent(t.dataset.id)}/pass/retry`, { method: "POST" }); upsert(S.shipments, r.shipment); S.passes[r.pass.id] = r.pass; render(); toast("Пропуск переоформлен"); }
      catch (e) { toast(e.message); }
    }
  });

  // ---------- старт ----------
  function gate(text, hint) {
    $("#gate").hidden = false;
    $("#app").hidden = true;
    if (text) $("#gate-text").textContent = text;
    if (hint !== undefined) $("#gate-hint").textContent = hint;
  }

  async function start() {
    if (!tg || !tg.initData) return gate("Откройте через бота");
    // Telegram кладёт свои параметры в #…; вкладку при открытии берём из ?tab= (кнопка «Открыть пульт»)
    if (!location.hash || location.hash.includes("tgWebApp")) {
      const tab = new URLSearchParams(location.search).get("tab") || "overview";
      history.replaceState(null, "", location.pathname + location.search + "#" + tab);
    }
    tg.ready();
    tg.expand();
    try { tg.setHeaderColor("#0B1220"); tg.setBackgroundColor("#0B1220"); tg.setBottomBarColor && tg.setBottomBarColor("#131C2E"); } catch (e) { /* старые клиенты */ }
    tg.MainButton.onClick(accept);
    tg.BackButton.onClick(() => history.length > 1 ? history.back() : go("shipments"));
    try {
      await auth();
      await loadAll();
    } catch (e) {
      return gate("Не удалось войти", e.message);
    }
    $("#gate").hidden = true;
    $("#app").hidden = false;
    setLive("poll");
    render();
    connectWs();
  }

  start();
})();
