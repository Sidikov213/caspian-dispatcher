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
import type { Alternative } from "@/lib/types";
import { useDashboard } from "@/lib/useDashboard";
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
  const selectedId = params.get("shipment");
  const panel = params.get("panel") === "alternatives" ? "alternatives" : "twin";
  const view = params.get("view") === "ledger" ? "ledger" : "map";
  const now = useNow(60_000);
  const secondNow = useNow(1000);

  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [hoverRoute, setHoverRoute] = useState<string | null>(null);

  const go = useCallback(
    (patch: { shipment?: string | null; panel?: string | null; view?: string | null }) => {
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
  const alertsVersion = d.alerts.map((a) => `${a.id}:${a.status}`).join(",");
  const alternatives = useAlternatives(selected && panel === "alternatives" ? selected.id : null, alertsVersion);

  const sortedAlts = useMemo(() => sortAlternatives(alternatives ?? []), [alternatives]);
  const previewRoute = useMemo(() => {
    if (panel !== "alternatives" || !selected) return null;
    const hovered = sortedAlts.find((a) => a.route.id === hoverRoute);
    return (hovered ?? sortedAlts.find((a) => !isWaitRoute(a.route)))?.route ?? null;
  }, [panel, selected, sortedAlts, hoverRoute]);

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
    <div className="flex h-full min-h-[640px] min-w-[1180px] flex-col">
      <AppHeader
        stats={d.stats}
        co2Pct={co2Pct}
        weather={weather}
        presets={d.presets}
        onScenario={(preset) => {
          go({ shipment: null, panel: null, view: null });
          setDismissed(new Set());
          d.runScenario(preset);
        }}
        onReset={() => {
          go({ shipment: null, panel: null, view: null });
          setDismissed(new Set());
          d.resetDemo();
        }}
      />
      <div className="relative flex min-h-0 flex-1">
        <ShipmentList
          shipments={d.shipments}
          nodes={d.nodes}
          selectedId={view === "map" ? (selected?.id ?? null) : null}
          view={view}
          onSelect={(id) => go({ shipment: id, panel: null, view: null })}
          onView={(v) => go({ view: v === "ledger" ? "ledger" : null, shipment: null, panel: null })}
        />
        {view === "ledger" ? (
          <LedgerView
            blocks={d.ledger}
            check={d.ledgerCheck}
            verifying={d.verifying}
            shipments={d.shipments}
            nodes={d.nodes}
            onVerify={() => d.verifyLedger()}
            onTamper={(index) => d.tamperLedger(index)}
          />
        ) : (
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
            />
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
                alternatives={alternatives}
                nodes={d.nodes}
                busy={busy}
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
                onAccept={() => accept(newAlert.id)}
                onReject={() => reject(newAlert.id)}
                onOther={() => go({ shipment: newAlert.items[0]?.shipment_id ?? null, panel: "alternatives" })}
                onClose={() => setDismissed((s) => new Set(s).add(newAlert.id))}
              />
            )}
            {toast && !showModal && <Toast {...toast} />}
          </div>
        )}
        {d.error && (
          <div className="absolute bottom-4 left-1/2 z-40 -translate-x-1/2 rounded-[8px] border border-[#FECACA] bg-risk-soft px-4 py-2 text-[12.5px] text-risk-text">
            {d.error}
          </div>
        )}
      </div>
    </div>
  );
}
