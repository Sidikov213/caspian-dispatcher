"use client";

import { useMemo } from "react";
import { divergentNodes, isWaitRoute, sortAlternatives } from "@/lib/derive";
import { formatHoursDelta, formatInt, formatPercent, formatRub, formatSignedPct, shipmentNumber, shortNodeName } from "@/lib/format";
import type { Alert, AlertOption, Alternative, GraphNode, RiskLevel, Route, Shipment } from "@/lib/types";
import { AlertDecisionNote } from "./AlertDecisionNote";
import { CloseIcon } from "./icons";

interface Props {
  shipment: Shipment;
  /** Новый алерт по этому грузу: варианты — его options. Без него — маршруты груза только для просмотра. */
  alert: Alert | null;
  /** Последний закрытый алерт по грузу — показать, чем кончился (status_note, кто принял). */
  closedAlert: Alert | null;
  /** null — ещё грузятся. */
  alternatives: Alternative[] | null;
  nodes: Map<string, GraphNode>;
  busy: boolean;
  /** Право decide_alert из /api/auth/me. */
  canDecide: boolean;
  onPreview(route: Route | null): void;
  onClose(): void;
  onAccept(alertId: string, optionId: string): void;
  onWait(alertId: string): void;
}

const RISK_COLOR: Record<RiskLevel, string> = { low: "var(--color-rerouted)", medium: "var(--color-warn)", high: "var(--color-risk)" };

function nodeName(nodes: Map<string, GraphNode>, id: string) {
  const n = nodes.get(id);
  return n ? shortNodeName(n.name) : id;
}

const cut = (t: string) => t.replace(/\s*\(.*\)\s*$/, "");

function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="min-w-0 flex-1">
      <div className="caps text-[9px] leading-[11px] font-bold text-muted">{label}</div>
      <div className="tnum mt-[8px] text-[15px] leading-[18px] font-bold whitespace-nowrap" style={{ color }}>
        {value}
      </div>
    </div>
  );
}

/** Карточка варианта алерта: числа — из Alert.options как есть (сумма по грузам алерта). */
function OptionCard({
  index,
  option,
  plan,
  alert,
  nodes,
  busy,
  canDecide,
  onPreview,
  onAccept,
  onWait,
}: {
  index: number;
  option: AlertOption;
  plan: Route | null;
  alert: Alert;
  nodes: Map<string, GraphNode>;
  busy: boolean;
  canDecide: boolean;
  onPreview(route: Route | null): void;
  onAccept(alertId: string, optionId: string): void;
  onWait(alertId: string): void;
}) {
  const wait = option.id === "wait";
  const rec = option.recommended && !wait;
  return (
    <section
      onMouseEnter={() => !wait && option.route && onPreview(option.route)}
      onMouseLeave={() => onPreview(null)}
      className="shrink-0 rounded-[12px] border px-[14px] pt-[12px] pb-[12px]"
      style={{ background: rec ? "var(--color-ok-soft)" : "var(--color-panel)", borderColor: rec ? "var(--color-ok-line)" : "var(--color-line)" }}
    >
      <div className="flex items-center justify-between">
        <div className="caps text-[10px] leading-[12px] font-bold" style={{ color: rec ? "var(--color-rerouted-text)" : "var(--color-muted)" }}>
          Вариант {String(index + 1).padStart(2, "0")}
        </div>
        {rec && <span className="rounded-[6px] bg-ok-soft px-[8px] py-[3px] text-[11px] font-bold text-rerouted-text">Рекомендуем</span>}
      </div>
      <h3 className="mt-[8px] text-[17px] leading-[22px] font-bold">{cut(option.title)}</h3>
      {option.route && !wait && (
        <div className="mt-[4px] truncate text-[12px] leading-[15px] text-muted">
          {divergentNodes(option.route, plan)
            .map((id) => nodeName(nodes, id))
            .join(" → ")}
        </div>
      )}
      <div className="mt-[14px] flex gap-[8px]">
        <Metric label="К плану" value={formatHoursDelta(option.delay_vs_plan_h)} />
        <Metric label="Экономия" value={formatRub(option.saved_rub)} color={option.saved_rub > 0 ? "var(--color-rerouted-text)" : undefined} />
        <Metric label="Груз-ч" value={formatInt(option.saved_hours)} />
        <Metric label="CO₂" value={`${option.co2_delta_kg > 0 ? "+" : ""}${formatInt(option.co2_delta_kg)} кг`} />
      </div>
      {canDecide && (
        <div className="mt-[12px] flex justify-end border-t border-line pt-[10px]">
          <button
            type="button"
            disabled={busy}
            onClick={() => (wait ? onWait(alert.id) : onAccept(alert.id, option.id))}
            className={`h-[40px] rounded-[8px] px-[18px] text-[13px] font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
              rec ? "bg-action text-white hover:bg-action-hover" : "border border-line-strong bg-panel text-text hover:bg-tile"
            }`}
          >
            {wait ? "Отклонить, ждать" : "Выбрать"}
          </button>
        </div>
      )}
    </section>
  );
}

/** Маршрут груза без угрозы — только просмотр. */
function RouteCard({ index, alt, plan, nodes, onPreview }: {
  index: number;
  alt: Alternative;
  plan: Route | null;
  nodes: Map<string, GraphNode>;
  onPreview(route: Route | null): void;
}) {
  const current = alt.recommended;
  return (
    <section
      onMouseEnter={() => onPreview(alt.route)}
      onMouseLeave={() => onPreview(null)}
      className="shrink-0 rounded-[12px] border border-line bg-panel px-[14px] pt-[12px] pb-[14px]"
    >
      <div className="caps text-[10px] leading-[12px] font-bold text-muted">
        {current ? "Текущий маршрут" : `Маршрут ${String(index + 1).padStart(2, "0")}`}
      </div>
      <div className="mt-[8px] truncate text-[14px] leading-[18px] font-bold">
        {divergentNodes(alt.route, current ? null : plan)
          .map((id) => nodeName(nodes, id))
          .join(" → ")}
      </div>
      <div className="mt-[12px] flex gap-[8px]">
        <Metric label="К плану" value={formatHoursDelta(alt.delta.hours)} />
        <Metric label="Стоимость" value={alt.delta.rub > 0 ? `+${formatRub(alt.delta.rub)}` : formatRub(alt.delta.rub)} />
        <Metric label="CO₂" value={`${alt.delta.co2_kg > 0 ? "+" : ""}${formatInt(alt.delta.co2_kg)} кг`} />
        <Metric label="Риск" value={formatPercent(alt.risk.miss_probability)} color={RISK_COLOR[alt.risk.level]} />
      </div>
    </section>
  );
}

export function AlternativesPanel({
  shipment,
  alert,
  closedAlert,
  alternatives,
  nodes,
  busy,
  canDecide,
  onPreview,
  onClose,
  onAccept,
  onWait,
}: Props) {
  const sorted = useMemo(() => sortAlternatives(alternatives ?? []), [alternatives]);
  // План нужен, чтобы показать, где вариант расходится с ним: исходный маршрут из алерта или текущий.
  const plan = alert?.items.find((i) => i.shipment_id === shipment.id)?.from_route ?? shipment.route;
  const options = alert?.options ?? [];

  return (
    <aside className="scroll-thin absolute inset-y-0 right-0 z-20 flex w-[400px] flex-col overflow-y-auto border-l border-line bg-panel pt-[20px] pr-5 pb-[27.5px] pl-[19px] shadow-[-8px_0_24px_var(--color-shadow)]">
      <button
        type="button"
        onClick={onClose}
        aria-label="Назад к грузу"
        className="absolute top-[25px] right-[21.5px] flex size-[35px] items-center justify-center rounded-[8px] border border-line bg-panel text-muted hover:bg-tile"
      >
        <CloseIcon size={16} />
      </button>

      <div className="caps pr-[44px] text-[10.5px] leading-[13px] font-bold text-muted">
        Груз <span className="tnum">{shipmentNumber(shipment.id)}</span> &nbsp;/&nbsp; {shipment.title}
      </div>
      <h2 className="mt-[13px] text-[22px] leading-[28px] font-bold">{alert ? "Варианты решения" : "Маршруты груза"}</h2>
      <p className="mt-[8px] text-[13px] leading-[17px] text-muted">
        {alert ? (
          <>
            {alert.title}
            {alert.source && <> · {alert.source === "forecast" ? "по прогнозу" : "сценарий"}</>}
            <br />
            Числа — сумма по {alert.items.length > 1 ? `${alert.items.length} грузам алерта` : "грузу"}, против ожидания следующего рейса
          </>
        ) : (
          "Угрозы по грузу нет — маршруты только для просмотра"
        )}
      </p>

      {alert && !canDecide && (
        <div className="mt-[14px]">
          <AlertDecisionNote alert={alert} />
        </div>
      )}
      {!alert && closedAlert && (
        <div className="mt-[14px]">
          <AlertDecisionNote alert={closedAlert} />
        </div>
      )}

      <div className="mt-[16px] flex flex-col gap-[12px]">
        {alert &&
          options.map((o, i) => (
            <OptionCard
              key={o.id}
              index={i}
              option={o}
              plan={plan}
              alert={alert}
              nodes={nodes}
              busy={busy}
              canDecide={canDecide}
              onPreview={onPreview}
              onAccept={onAccept}
              onWait={onWait}
            />
          ))}
        {alert && options.length === 0 && <div className="pt-6 text-center text-[13px] text-muted">У алерта нет вариантов решения</div>}
        {!alert && alternatives === null && <div className="pt-6 text-center text-[13px] text-muted">Загружаем маршруты…</div>}
        {!alert &&
          sorted
            .filter((a) => !isWaitRoute(a.route))
            .map((alt, i) => <RouteCard key={alt.route.id} index={i} alt={alt} plan={plan} nodes={nodes} onPreview={onPreview} />)}
      </div>
      {alert && (
        <p className="mt-[14px] text-[12px] leading-[16px] text-muted">
          До наступления события деньги и часы — расчётная экономия. {formatSignedPct(alert.totals.co2_delta_pct)} CO₂ — у
          рекомендованного варианта.
        </p>
      )}
    </aside>
  );
}
