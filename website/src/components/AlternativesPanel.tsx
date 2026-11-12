"use client";

import { useMemo } from "react";
import { divergentNodes, isWaitRoute, optionFor, optionTitle, sortAlternatives } from "@/lib/derive";
import { formatHoursDelta, formatPercent, formatRub, formatSignedPct, shipmentNumber, shortNodeName } from "@/lib/format";
import type { Alert, Alternative, GraphNode, RiskLevel, Route, Shipment } from "@/lib/types";
import { CloseIcon } from "./icons";

interface Props {
  shipment: Shipment;
  /** Новый алерт по этому грузу; без него варианты можно только смотреть. */
  alert: Alert | null;
  /** null — ещё грузятся. */
  alternatives: Alternative[] | null;
  nodes: Map<string, GraphNode>;
  busy: boolean;
  onPreview(routeId: string | null): void;
  onClose(): void;
  onAccept(alertId: string, optionId: string): void;
  onWait(alertId: string): void;
}

const RISK_COLOR: Record<RiskLevel, string> = { low: "#15803D", medium: "#B45309", high: "#DC2626" };

function nodeName(nodes: Map<string, GraphNode>, id: string) {
  const n = nodes.get(id);
  return n ? shortNodeName(n.name) : id;
}

/** «+17 тыс ₽», «0 ₽» — доплата к плановой стоимости перевозки. */
function surcharge(rub: number): string {
  return rub > 0 ? `+${formatRub(rub)}` : formatRub(rub);
}

/** Изменение CO₂ к плановому маршруту: плановый итог = итог варианта минус дельта. */
function co2Pct(alt: Alternative): number {
  const base = alt.route.total_co2_kg - alt.delta.co2_kg;
  return base > 0 ? (alt.delta.co2_kg / base) * 100 : 0;
}

function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="w-[86px]">
      <div className="caps text-[9px] leading-[11px] font-bold text-muted">{label}</div>
      <div className="tnum mt-[8.5px] text-[12.5px] leading-[16px] font-bold whitespace-nowrap" style={{ color }}>
        {value}
      </div>
    </div>
  );
}

function OptionCard({
  index,
  alt,
  plan,
  waitHours,
  alert,
  nodes,
  busy,
  onPreview,
  onAccept,
  onWait,
}: {
  index: number;
  alt: Alternative;
  plan: Route | null;
  waitHours: number | null;
  alert: Alert | null;
  nodes: Map<string, GraphNode>;
  busy: boolean;
  onPreview(routeId: string | null): void;
  onAccept(alertId: string, optionId: string): void;
  onWait(alertId: string): void;
}) {
  const option = optionFor(alt, alert);
  const wait = isWaitRoute(alt.route);
  const rec = alt.recommended && !wait;
  const faster = waitHours !== null && !wait ? Math.round(waitHours - alt.delta.hours) : null;
  const canPick = !!alert && !busy && (wait || !!option);

  const foot = wait
    ? "Базовый сценарий"
    : faster !== null && faster > 0
      ? `на ${faster}\u00A0ч быстрее ожидания`
      : `${formatHoursDelta(alt.delta.hours)} к плану`;

  return (
    <section
      onMouseEnter={() => !wait && onPreview(alt.route.id)}
      onMouseLeave={() => onPreview(null)}
      className="h-[197px] shrink-0 rounded-[12px] border pr-[14px] pl-[14px]"
      style={{
        background: rec ? "#F0FDF4" : "#FFFFFF",
        borderColor: rec ? "#86EFAC" : "#DFE6EF",
      }}
    >
      <div className="relative pt-[12px]">
        <div className="caps text-[10px] leading-[12px] font-bold" style={{ color: rec ? "#15803D" : "#64748B" }}>
          Вариант {String(index + 1).padStart(2, "0")}
        </div>
        {rec && (
          <span className="absolute top-[10px] right-[1px] flex h-[21px] w-[106px] items-center justify-center rounded-[6px] bg-[#DCFCE7] text-[11px] font-bold text-ok">
            Рекомендуем
          </span>
        )}
      </div>
      <h3 className="mt-[10px] truncate text-[18px] leading-[22px] font-bold">{optionTitle(option, alt)}</h3>
      <div className="mt-[5px] truncate text-[11px] leading-[14px] text-muted">
        {divergentNodes(alt.route, plan)
          .map((id) => nodeName(nodes, id))
          .join(" → ")}
      </div>

      <div className="mt-[16.5px] flex">
        <Metric label="Задержка" value={formatHoursDelta(alt.delta.hours)} />
        <Metric label="Стоимость" value={surcharge(alt.delta.rub)} />
        <Metric label="CO₂" value={formatSignedPct(co2Pct(alt))} />
        <Metric label="Риск" value={formatPercent(alt.risk.miss_probability)} color={RISK_COLOR[alt.risk.level]} />
      </div>

      <div className="mt-[8px] h-px bg-line" />
      <div className="mt-[8px] flex items-center justify-between">
        <span className="text-[10.5px] leading-[14px] text-muted">{foot}</span>
        <button
          type="button"
          disabled={!canPick}
          onClick={() => alert && (wait ? onWait(alert.id) : option && onAccept(alert.id, option.id))}
          className={`h-[39px] w-[106px] rounded-[9px] text-[13px] font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
            rec ? "bg-action text-white hover:bg-action-hover" : "border border-line-strong bg-panel text-text hover:bg-tile"
          }`}
        >
          Выбрать
        </button>
      </div>
    </section>
  );
}

export function AlternativesPanel({
  shipment,
  alert,
  alternatives,
  nodes,
  busy,
  onPreview,
  onClose,
  onAccept,
  onWait,
}: Props) {
  const sorted = useMemo(() => sortAlternatives(alternatives ?? []), [alternatives]);
  // План нужен, чтобы показать, где вариант расходится с ним: из списка или из алерта.
  const plan = useMemo(
    () =>
      sorted.find((a) => isWaitRoute(a.route))?.route ??
      alert?.items.find((i) => i.shipment_id === shipment.id)?.from_route ??
      null,
    [sorted, alert, shipment.id],
  );
  const waitHours = sorted.find((a) => isWaitRoute(a.route))?.delta.hours ?? null;
  const [num, name] = [shipmentNumber(shipment.id), shipment.title];

  return (
    <aside className="scroll-thin absolute inset-y-0 right-0 z-20 flex w-[400px] flex-col overflow-y-auto border-l border-line bg-panel pt-[20px] pr-5 pb-[27.5px] pl-[19px] shadow-[-8px_0_24px_rgba(18,48,74,0.06)]">
      <button
        type="button"
        onClick={onClose}
        aria-label="Назад к грузу"
        className="absolute top-[25px] right-[21.5px] flex size-[35px] items-center justify-center rounded-[8px] border border-line bg-panel text-muted hover:bg-tile"
      >
        <CloseIcon size={16} />
      </button>

      <div className="caps text-[10.5px] leading-[13px] font-bold text-cyan">
        Груз <span className="tnum">{num}</span> &nbsp;/&nbsp; {name}
      </div>
      <h2 className="mt-[13px] text-[22px] leading-[28px] font-bold">Альтернативные маршруты</h2>
      <p className="mt-[8px] text-[12.5px] leading-[16px] text-muted">Сравнение с ожиданием парома</p>

      <div className="mt-[16px] flex flex-col gap-[13px]">
        {alternatives === null && <div className="pt-6 text-center text-[12.5px] text-muted">Считаем маршруты…</div>}
        {alternatives?.length === 0 && (
          <div className="pt-6 text-center text-[12.5px] text-muted">Для этого груза нет вариантов: маршрут не под угрозой.</div>
        )}
        {sorted.map((alt, i) => (
          <OptionCard
            key={alt.route.id}
            index={i}
            alt={alt}
            plan={plan}
            waitHours={waitHours}
            alert={alert}
            nodes={nodes}
            busy={busy}
            onPreview={onPreview}
            onAccept={onAccept}
            onWait={onWait}
          />
        ))}
      </div>
    </aside>
  );
}
