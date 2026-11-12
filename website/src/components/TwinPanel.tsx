"use client";

import { useState } from "react";
import { cargoLabel, checkpointLabel, co2ByMode, modeIcon, routeStops, type RouteStop } from "@/lib/derive";
import {
  formatDateTime,
  formatHoursDelta,
  formatInt,
  formatPercent,
  formatTime,
  sameMskDay,
  shipmentNumber,
  shortNodeName,
} from "@/lib/format";
import type { Edge, GraphNode, Pass, RiskLevel, Shipment } from "@/lib/types";
import { CloseIcon, FileIcon, LeafIcon, RouteIcon, TransportIcon } from "./icons";
import { QrCode } from "./QrCode";
import { PassModal } from "./PassModal";
import { StatusChip } from "./StatusChip";

interface Props {
  shipment: Shipment;
  nodes: Map<string, GraphNode>;
  edges: Map<string, Edge>;
  pass: Pass | null;
  onClose(): void;
  onAlternatives?(): void;
}

const RISK_TONE: Record<RiskLevel, { bg: string; border: string; text: string }> = {
  high: { bg: "var(--color-risk-soft)", border: "var(--color-risk-line)", text: "var(--color-risk)" },
  medium: { bg: "var(--color-warn-soft)", border: "var(--color-warn-line)", text: "var(--color-warn)" },
  low: { bg: "var(--color-ok-soft)", border: "var(--color-ok-line)", text: "var(--color-rerouted)" },
};

function nodeName(nodes: Map<string, GraphNode>, id: string) {
  const n = nodes.get(id);
  return n ? shortNodeName(n.name) : id;
}

function stopTime(stop: RouteStop): string {
  if (!stop.forecast) return `${formatDateTime(stop.planned)}${stop.tone === "done" ? " ✓" : ""}`;
  const to = sameMskDay(stop.planned, stop.forecast) ? formatTime(stop.forecast) : formatDateTime(stop.forecast);
  return `${formatDateTime(stop.planned)} → ${to}`;
}

function RiskCard({ shipment }: { shipment: Shipment }) {
  const risk = shipment.risk;
  if (!risk) return null;
  const tone = RISK_TONE[risk.level];
  const maxImpact = Math.max(...risk.factors.map((f) => f.impact_hours), 1);
  const shift = risk.departure_shift_h;
  // паром на маршруте — этап с рейсом; без него груз идёт по суше и риск — на границе
  const ferry = shipment.route.legs.some((l) => !!l.sailing_id);

  return (
    <section
      className="mt-[18.5px] shrink-0 rounded-[12px] border pt-[10.5px] pr-[16px] pb-[13px] pl-[13.5px]"
      style={{ background: tone.bg, borderColor: tone.border }}
    >
      <div className="caps text-[10.5px] leading-[13px] font-bold" style={{ color: tone.text }}>
        Риск срыва стыковки
      </div>
      <div className="flex">
        <div className="w-[223.5px]">
          <div className="tnum mt-[3px] text-[40px] leading-[44px] font-bold" style={{ color: tone.text }}>
            {formatPercent(risk.miss_probability)}
          </div>
          <div className="mt-[3.5px] text-[11.5px] leading-[16px] text-muted">
            {ferry ? "Вероятность опоздать на паром" : "Риск задержки на границе"}
          </div>
        </div>
        <div className="pt-[11.5px]">
          <div className="tnum text-[24px] leading-[28px] font-bold">{formatHoursDelta(shift)}</div>
          <div className="mt-[-1px] text-[11.5px] leading-[14px] text-muted">
            {shift > 0 ? "позже планового рейса" : "по расписанию"}
          </div>
        </div>
      </div>
      {risk.arrival_delay_h > 0 && (
        <div className="mt-[6px] text-[13px] leading-[18px] font-bold" style={{ color: tone.text }}>
          Если рейс отменят: прибытие {formatHoursDelta(risk.arrival_delay_h)}
        </div>
      )}
      {risk.factors.length > 0 && (
        <ul className="mt-[6px]">
          {risk.factors.map((f, i) => (
            <li key={f.name} className="flex h-[19px] items-center text-[11.5px]">
              <span className="w-[158.5px] truncate">{f.label}</span>
              <span className="relative h-[4px] w-[121px] overflow-hidden rounded-full bg-panel/[0.08]">
                <span
                  className="absolute inset-y-0 left-0 rounded-full"
                  style={{
                    width: `${Math.max((f.impact_hours / maxImpact) * 100, 4)}%`,
                    background: i === 0 && risk.level === "high" ? "var(--color-risk)" : "var(--color-warn)",
                  }}
                />
              </span>
              <span className="tnum ml-auto font-bold">{formatHoursDelta(f.impact_hours)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Stops({ shipment, nodes }: { shipment: Shipment; nodes: Map<string, GraphNode> }) {
  const stops = routeStops(shipment);
  return (
    <ol className="mt-[10px] shrink-0">
      {stops.map((stop, i) => {
        const danger = stop.tone === "danger";
        return (
          <li key={`${stop.nodeId}-${i}`} className="relative flex h-[46px] last:h-[29.5px]">
            {i < stops.length - 1 && <span className="absolute top-[29.5px] left-[14.5px] h-[16.5px] w-px bg-line-strong" />}
            <span
              className="flex size-[29.5px] shrink-0 items-center justify-center rounded-[7px]"
              style={{ background: danger ? "var(--color-risk-soft)" : "var(--color-info-soft)", color: danger ? "var(--color-risk)" : "var(--color-transit)" }}
            >
              <TransportIcon kind={modeIcon(stop.mode)} size={15} />
            </span>
            <div className="ml-[12.5px] min-w-0 flex-1">
              <div className="flex items-baseline">
                <span className="truncate text-[14px] leading-[17px] font-bold">{nodeName(nodes, stop.nodeId)}</span>
                <span
                  className="tnum ml-auto pl-3 text-[11.5px] whitespace-nowrap"
                  style={{ color: danger ? "var(--color-risk)" : "var(--color-muted)" }}
                >
                  {stopTime(stop)}
                </span>
              </div>
              <div className="mt-[1px] truncate text-[11.5px] leading-[14px] text-muted">{stop.note}</div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function Co2Card({ shipment, edges }: { shipment: Shipment; edges: Map<string, Edge> }) {
  const parts = co2ByMode(shipment, edges);
  const total = shipment.route.total_co2_kg || parts.rail + parts.sea + parts.road;
  const sum = parts.rail + parts.sea + parts.road || 1;
  const segments = [
    { key: "rail", label: "Ж/д", value: parts.rail, color: "var(--color-transit)" },
    { key: "sea", label: "Море", value: parts.sea, color: "var(--color-cyan)" },
    { key: "road", label: "Авто", value: parts.road, color: "var(--color-rerouted)" },
  ].filter((p) => p.value > 0);

  return (
    <section className="mt-[19px] h-[79px] shrink-0 rounded-[12px] border border-line bg-bg pt-[11px] pr-[13.5px] pl-[11.5px]">
      <div className="flex items-center">
        <LeafIcon size={15} className="text-rerouted" />
        <span className="ml-[8.5px] text-[14px] leading-[17px] font-bold">Выбросы CO₂</span>
        <span className="tnum ml-auto text-[18px] leading-[20px] font-bold">{formatInt(total)}&nbsp;кг</span>
      </div>
      <div className="mt-[8.5px] flex gap-[3px] pl-[0.5px]">
        {segments.map((p) => (
          <span key={p.key} className="h-[4.5px] rounded-full" style={{ flexGrow: p.value / sum, background: p.color }} />
        ))}
      </div>
      <div className="tnum mt-[10px] flex text-[11.5px] leading-[14px] whitespace-pre text-muted">
        {segments.map((p, i) => (
          <span key={p.key}>
            {i > 0 && <span className="px-[10px]">·</span>}
            {p.label}  {formatInt(p.value)}
            {i === segments.length - 1 ? " кг" : ""}
          </span>
        ))}
      </div>
    </section>
  );
}

function PassCard({ shipment, pass, nodes }: { shipment: Shipment; pass: Pass | null; nodes: Map<string, GraphNode> }) {
  const [open, setOpen] = useState(false);
  const checkpoint = pass ? nodes.get(pass.checkpoint_node) : null;
  const where = pass ? checkpointLabel(checkpoint ?? undefined, pass.checkpoint_node) : "";

  let title = "Пропуск оформлен";
  let sub = where;
  let color = "var(--color-text)";
  if (shipment.pass_state === "reissue_pending") {
    title = "Пропуск ожидает переоформления";
    sub = pass ? `Действует старый: ${where}` : "Маршрут изменён";
    color = "var(--color-warn)";
  } else if (shipment.pass_state === "none" || !shipment.pass_id) {
    title = "Пропуск не оформлен";
    sub = "Нужен снимок инвойса в приложении";
    color = "var(--color-muted)";
  }

  return (
    <section className="mt-[11.5px] flex h-[73.5px] shrink-0 items-center rounded-[12px] border border-line bg-bg pr-[13px] pl-[11.5px]">
      <span className="flex size-[34px] shrink-0 items-center justify-center rounded-[8px] bg-tile text-muted">
        <FileIcon size={15} />
      </span>
      <div className="ml-[11.5px] min-w-0 flex-1">
        <div className="truncate text-[14px] leading-[17px] font-bold" style={{ color }}>
          {title}
        </div>
        <div className="mt-[4px] truncate text-[11.5px] leading-[14px] text-muted">{sub}</div>
      </div>
      {pass && shipment.pass_state !== "none" && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Открыть пропуск"
          title="Открыть пропуск"
          className="ml-3 flex size-[48.5px] shrink-0 cursor-zoom-in items-center justify-center rounded-[8px] bg-panel ring-action hover:ring-2"
        >
          <QrCode value={pass.token} size={39} />
        </button>
      )}
      {open && pass && <PassModal pass={pass} shipment={shipment} nodes={nodes} onClose={() => setOpen(false)} />}
    </section>
  );
}

export function TwinPanel({ shipment, nodes, edges, pass, onClose, onAlternatives }: Props) {
  return (
    <aside className="scroll-thin absolute inset-y-0 right-0 z-20 flex w-[400px] flex-col overflow-y-auto border-l border-line bg-panel pt-[20px] pr-[20.5px] pb-[27.5px] pl-[20px] shadow-[-8px_0_24px_var(--color-shadow)]">
      <button
        type="button"
        onClick={onClose}
        aria-label="Закрыть"
        className="absolute top-[25px] right-[21.5px] flex size-[35px] items-center justify-center rounded-[8px] border border-line bg-panel text-muted hover:bg-tile"
      >
        <CloseIcon size={16} />
      </button>

      <div className="caps text-[10.5px] leading-[13px] font-bold text-cyan">Цифровой двойник</div>
      <h2 className="mt-[9.5px] text-[26px] leading-[32px] font-bold">
        <span className="tnum">{shipmentNumber(shipment.id)}</span> {shipment.title}
      </h2>
      <div className="mt-px flex h-[16px] items-center pr-[10px]">
        <span className="text-[12.5px] leading-[16px] text-muted">
          {formatInt(shipment.weight_t)}&nbsp;т · {cargoLabel(shipment.cargo_type)}
        </span>
        <span className="ml-auto">
          <StatusChip status={shipment.display_status} />
        </span>
      </div>

      <RiskCard shipment={shipment} />

      <div className="mt-[17.5px] flex items-baseline pr-[19.5px]">
        <h3 className="text-[18px] leading-[22px] font-bold">Этапы маршрута</h3>
        <span className="ml-auto text-[11.5px] text-muted">План / прогноз</span>
      </div>
      <Stops shipment={shipment} nodes={nodes} />

      <Co2Card shipment={shipment} edges={edges} />
      <PassCard shipment={shipment} pass={shipment.pass_id ? pass : null} nodes={nodes} />

      <button
        type="button"
        onClick={onAlternatives}
        className="mt-[21.5px] flex h-[47px] shrink-0 items-center justify-center gap-[12px] rounded-[8px] bg-action text-[15px] font-bold text-white transition-colors hover:bg-action-hover"
      >
        <RouteIcon size={16} />
        Альтернативные маршруты
      </button>
    </aside>
  );
}
