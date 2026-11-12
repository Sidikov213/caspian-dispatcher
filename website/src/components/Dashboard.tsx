"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import {
  checkpointLabel,
  divergenceNode,
  isWaitRoute,
  newAlertFor,
  pickFocus,
  sortAlternatives,
  stormScope,
  weatherSummary,
} from "@/lib/derive";
import { minutesAgo } from "@/lib/format";
import { can, useSessionUser } from "@/lib/session";
import type { Alternative, Route } from "@/lib/types";
import { useDashboard } from "@/lib/useDashboard";
import { DecisionsSection } from "./sections/DecisionsSection";
import { DataSection } from "./sections/DataSection";
import { ModelSection } from "./sections/ModelSection";
import { NodeCard } from "./NodeCard";
import { PassesTable } from "./sections/PassesTable";
import { SailingsSection } from "./sections/SailingsSection";
import { ShipmentsSection } from "./sections/ShipmentsSection";
import { SECTIONS, SideNav, type Section } from "./SideNav";
import { AlertModal } from "./AlertModal";
import { AlternativesPanel } from "./AlternativesPanel";
import { AppHeader } from "./AppHeader";
import { RealMap } from "./RealMap";
import { LedgerView } from "./LedgerView";
import { ShipmentList } from "./ShipmentList";
import { Toast } from "./Toast";
import { TwinPanel } from "./TwinPanel";

const PANEL_W = 400;
const TOAST_MS = 7000;

function useNow(intervalMs: number) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

/** Альтернативы груза; перезапрашиваются при смене алертов и маршрута. */
function useAlternatives(shipmentId: string | null, version: string) {
  const key = shipmentId ? `${shipmentId}|${version}` : null;
  const [loaded, setLoaded] = useState<{ key: string; list: Alternative[] } | null>(null);
  useEffect(() => {
    if (!key || !shipmentId) return;
    let cancelled = false;
    api
      .getAlternatives(shipmentId)
      .catch(() => [] as Alternative[])
      .then((list) => !cancelled && setLoaded({ key, list }));
    return () => {
      cancelled = true;
    };
  }, [key, shipmentId]);
  return loaded && loaded.key === key ? loaded.list : null;
}

export function Dashboard() {
  const d = useDashboard();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const user = useSessionUser();
  const canDecide = can(user, "decide_alert");
  const selectedId = params.get("shipment");
  const panel = params.get("panel") === "alternatives" ? "alternatives" : "twin";
  // Раздел в адресе (?s=): статический экспорт без отдельных страниц. Экспедитор по умолчанию — «Грузы».
  const sParam = params.get("s") as Section | null;
  const section: Section = sParam && SECTIONS.includes(sParam) ? sParam : user?.role === "expeditor" ? "shipments" : "pult";
  const view = section === "pult" ? "map" : "other";
  const now = useNow(60_000);
  const secondNow = useNow(1000);

  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [hoverRoute, setHoverRoute] = useState<Route | null>(null);
  const [nodeCard, setNodeCard] = useState<string | null>(null);

  const go = useCallback(
    (patch: { shipment?: string | null; panel?: string | null; s?: string | null }) => {
      const next = new URLSearchParams(params.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v) next.set(k, v);
        else next.delete(k);
      }
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, pathname, router],
  );

  const selected = d.shipments.find((s) => s.id === selectedId) ?? null;
  const pass = selected?.pass_id ? (d.passes.get(selected.pass_id) ?? null) : null;
  // Решение принято: угроза снята, шапка и плашки волны показывают текущее состояние моря (макеты W5, W6).
  const calm = d.alerts.some((a) => a.status === "accepted");
  const weather = useMemo(() => weatherSummary(d.weather, d.scenario, calm), [d.weather, d.scenario, calm]);
  const zone = useMemo(() => stormScope(d.weather), [d.weather]);

  // ---------- алерт и варианты ----------
  const newAlert = d.alerts.find((a) => a.status === "new") ?? null;
  const showModal = !!newAlert && !dismissed.has(newAlert.id) && !selected && view === "map";
  const selectedAlert = selected ? newAlertFor(d.alerts, selected.id) : null;
  const closedAlert = useMemo(() => {
    if (!selected) return null;
    const mine = d.alerts.filter((a) => a.status !== "new" && a.items.some((i) => i.shipment_id === selected.id));
    return mine.sort((a, b) => Date.parse(b.accepted_at ?? b.created_at) - Date.parse(a.accepted_at ?? a.created_at))[0] ?? null;
  }, [d.alerts, selected]);
  const alertsVersion = d.alerts.map((a) => `${a.id}:${a.status}`).join(",");
  const alternatives = useAlternatives(selected && panel === "alternatives" ? selected.id : null, alertsVersion);

  const sortedAlts = useMemo(() => sortAlternatives(alternatives ?? []), [alternatives]);
  const previewRoute = useMemo(() => {
    if (panel !== "alternatives" || !selected) return null;
    if (hoverRoute) return hoverRoute;
    // С алертом — рекомендованный вариант из Alert.options; без него — первый маршрут груза.
    if (selectedAlert) return selectedAlert.options.find((o) => o.recommended && o.id !== "wait")?.route ?? null;
    return sortedAlts.find((a) => !isWaitRoute(a.route) && !a.recommended)?.route ?? null;
  }, [panel, selected, sortedAlts, hoverRoute, selectedAlert]);

  // Сброс демо (свой или demo.reset из WebSocket): закрыть двойник, варианты и окна, показать алерты заново.
  const [seenReset, setSeenReset] = useState(d.resetSeq);
  if (seenReset !== d.resetSeq) {
    setSeenReset(d.resetSeq);
    setDismissed(new Set());
    setHoverRoute(null);
  }
  useEffect(() => {
    if (d.resetSeq === 0) return;
    const next = new URLSearchParams(window.location.search);
    if (!next.has("shipment") && !next.has("panel")) return;
    next.delete("shipment");
    next.delete("panel");
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }, [d.resetSeq, pathname, router]);

  const focus = pickFocus(d.shipments, selected?.id ?? null);
  const checkpointNode = useMemo(() => {
    if (previewRoute && focus) return divergenceNode(previewRoute, focus.route);
    if (focus?.rerouted && focus.pass_id) return d.passes.get(focus.pass_id)?.checkpoint_node ?? null;
    return null;
  }, [previewRoute, focus, d.passes]);

  const accept = useCallback(
    async (alertId: string, optionId?: string) => {
      setBusy(true);
      const res = await d.accept(alertId, optionId);
      setBusy(false);
      if (res) go({ shipment: null, panel: null });
    },
    [d, go],
  );

  const reject = useCallback(
    async (alertId: string) => {
      setBusy(true);
      const ok = await d.reject(alertId);
      setBusy(false);
      if (ok) go({ shipment: null, panel: null });
    },
    [d, go],
  );

  // Счётчик CO₂ приходит из /stats: 6.9 значит «−6,9%». Старые моки без поля — считаем по алертам.
  const co2Pct = useMemo(() => {
    if (d.stats && typeof d.stats.co2_saved_pct === "number") return -d.stats.co2_saved_pct;
    let delta = 0;
    let base = 0;
    for (const a of d.alerts) {
      if (a.status !== "accepted" || !a.totals.co2_delta_pct) continue;
      delta += a.totals.co2_delta_kg;
      base += (a.totals.co2_delta_kg / a.totals.co2_delta_pct) * 100;
    }
    return base ? (delta / base) * 100 : 0;
  }, [d.stats, d.alerts]);

  const freshness = useMemo(() => {
    if (!d.weather) return null;
    const m = minutesAgo(d.weather.updated_at, now);
    const text = m < 1 ? "Погода обновлена только что" : `Погода обновлена ${m} мин назад`;
    return { text, stale: d.weather.stale || m > 60 };
  }, [d.weather, now]);

  // ---------- подтверждение «Маршрут изменён» ----------
  const toast = useMemo(() => {
    if (!d.justAccepted || secondNow - d.justAccepted.at > TOAST_MS || view !== "map") return null;
    const alert = d.alerts.find((a) => a.id === d.justAccepted?.id);
    if (!alert) return null;
    const pending = alert.items.some((i) => d.shipments.find((s) => s.id === i.shipment_id)?.pass_state === "reissue_pending");
    if (pending) return { tone: "warn" as const, title: "Маршрут изменён", text: "Пропуск ожидает переоформления · старый действует" };
    // Где выдан новый пропуск: у перехода («для перехода Астара») или у порта («на порт Махачкала»).
    const first = d.shipments.find((s) => s.id === alert.items[0]?.shipment_id);
    const cpId = first?.pass_id ? d.passes.get(first.pass_id)?.checkpoint_node : null;
    const cp = cpId ? d.nodes.get(cpId) : undefined;
    const cpName = cp ? checkpointLabel(cp, cpId ?? "").replace(/^(порт|пункт пропуска)\s+/, "") : null;
    const where = !cpName ? "" : cp?.type === "border" ? ` для перехода ${cpName}` : ` на порт ${cpName}`;
    return {
      tone: "ok" as const,
      title: "Маршрут изменён",
      text: `${alert.items.length > 1 ? "Пропуска переоформлены" : "Пропуск переоформлен"}${where}`,
    };
  }, [d.justAccepted, d.alerts, d.shipments, d.passes, d.nodes, secondNow, view]);

  const panelOpen = !!selected && view === "map";

  return (
    <div className="flex h-full min-h-[640px] min-w-[1280px] flex-col">
      <AppHeader
        stats={d.stats}
        co2Pct={co2Pct}
        weather={weather}
        presets={d.presets}
        onScenario={(preset) => {
          go({ shipment: null, panel: null, s: "pult" });
          setDismissed(new Set());
          d.runScenario(preset);
        }}
        onReset={() => {
          go({ shipment: null, panel: null });
          setDismissed(new Set());
          d.resetDemo();
        }}
      />
      <div className="relative flex min-h-0 flex-1">
        <SideNav
          active={section}
          badges={{
            pult: { value: d.alerts.filter((a) => a.status === "new").length, tone: "risk" },
            shipments: { value: d.stats?.at_risk ?? 0, tone: "risk" },
          }}
          onSelect={(id) => go({ s: id === "pult" && user?.role !== "expeditor" ? null : id, shipment: null, panel: null })}
        />
        {section === "shipments" && (
          <ShipmentsSection
            shipments={d.shipments}
            nodes={d.nodes}
            passes={d.passes}
            canCreate
            onOpen={(id) => go({ s: "pult", shipment: id, panel: null })}
            onCreate={d.createShipment}
          />
        )}
        {section === "sailings" && <SailingsSection sailings={d.sailings} nodes={d.nodes} shipments={d.shipments} />}
        {section === "decisions" && <DecisionsSection alerts={d.alerts} />}
        {section === "model" && <ModelSection />}
        {section === "data" && <DataSection />}
        {section === "journal" && (
          <LedgerView
            blocks={d.ledger}
            check={d.ledgerCheck}
            verifying={d.verifying}
            shipments={d.shipments}
            nodes={d.nodes}
            canTamper={can(user, "reset_demo")}
            onVerify={() => d.verifyLedger()}
            onTamper={(index) => d.tamperLedger(index)}
          >
            <PassesTable version={`${d.ledger.length}:${d.resetSeq}`} shipments={d.shipments} nodes={d.nodes} />
          </LedgerView>
        )}
        {section === "pult" && (
          <ShipmentList
            shipments={d.shipments}
            nodes={d.nodes}
            selectedId={selected?.id ?? null}
            onSelect={(id) => go({ shipment: id, panel: null })}
          />
        )}
        {section === "pult" && (
          <div className="relative flex min-w-0 flex-1">
            <RealMap
              nodes={d.nodes}
              edges={d.edges}
              shipments={d.shipments}
              weather={d.weather}
              focusId={selected?.id ?? null}
              preview={previewRoute}
              stormZone={zone}
              zone={d.scenario && d.alerts.some((a) => a.scenario_id === d.scenario?.id) ? d.scenario.zone : null}
              alerts={d.alerts}
              calmWaves={calm}
              checkpointNode={checkpointNode}
              insetRight={panelOpen ? PANEL_W : 0}
              freshness={freshness}
              onSelect={(id) => go({ shipment: id, panel: null })}
              onNode={(id) => setNodeCard(id)}
            />
            {nodeCard && d.nodes.get(nodeCard) && (
              <NodeCard node={d.nodes.get(nodeCard)!} insetRight={panelOpen ? PANEL_W : 0} onClose={() => setNodeCard(null)} />
            )}
            {selected && panel === "twin" && (
              <TwinPanel
                shipment={selected}
                nodes={d.nodes}
                edges={d.edges}
                pass={pass}
                onClose={() => go({ shipment: null, panel: null })}
                onAlternatives={() => go({ panel: "alternatives" })}
              />
            )}
            {selected && panel === "alternatives" && (
              <AlternativesPanel
                shipment={selected}
                alert={selectedAlert}
                closedAlert={closedAlert}
                alternatives={alternatives}
                nodes={d.nodes}
                busy={busy}
                canDecide={canDecide}
                onPreview={setHoverRoute}
                onClose={() => go({ panel: null })}
                onAccept={(alertId, optionId) => accept(alertId, optionId)}
                onWait={(alertId) => reject(alertId)}
              />
            )}
            {showModal && newAlert && (
              <AlertModal
                alert={newAlert}
                scenario={d.scenario}
                weather={d.weather}
                shipments={d.shipments}
                nodes={d.nodes}
                busy={busy}
                canDecide={canDecide}
                onAccept={(optionId) => accept(newAlert.id, optionId)}
                onReject={() => reject(newAlert.id)}
                onOther={() => go({ shipment: newAlert.items[0]?.shipment_id ?? null, panel: "alternatives" })}
                onClose={() => setDismissed((s) => new Set(s).add(newAlert.id))}
              />
            )}
            {toast && !showModal && <Toast {...toast} />}
          </div>
        )}
        {d.error && (
          <div className="absolute bottom-4 left-1/2 z-40 -translate-x-1/2 rounded-[8px] border border-[var(--color-risk-line)] bg-risk-soft px-4 py-2 text-[12.5px] text-risk-text">
            {d.error}
          </div>
        )}
      </div>
    </div>
  );
}
