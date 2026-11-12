"use client";

import { shipmentNumber, formatHoursDelta, formatRub, formatSignedPct, shortNodeName } from "@/lib/format";
import { stormLeadHours, stormScope } from "@/lib/derive";
import type { Alert, GraphNode, Scenario, Shipment, Weather } from "@/lib/types";
import { CheckIcon, CloseIcon, StormIcon } from "./icons";

interface Props {
  alert: Alert;
  scenario: Scenario | null;
  weather: Weather | null;
  shipments: Shipment[];
  nodes: Map<string, GraphNode>;
  busy: boolean;
  onAccept(): void;
  onOther(): void;
  onReject(): void;
  onClose(): void;
}

function name(nodes: Map<string, GraphNode>, id: string) {
  const n = nodes.get(id);
  return n ? shortNodeName(n.name) : id;
}

/** «Шторм закроет переправу Астрахань — Энзели» по заблокированному этапу рекомендованного плана. */
function headline(alert: Alert, scenario: Scenario | null, weather: Weather | null, nodes: Map<string, GraphNode>): string {
  if ((!scenario || scenario.type === "storm") && stormScope(weather) === "full") return "Шторм остановит паромы\nна всём Каспии";
  const blocked = alert.items.flatMap((i) => i.from_route?.legs ?? []).find((l) => l.status === "blocked");
  if (!blocked || (scenario && scenario.type !== "storm")) return alert.title;
  return `Шторм закроет ${blocked.mode === "sea" ? "переправу" : "участок"}\n${name(nodes, blocked.from)} — ${name(nodes, blocked.to)}`;
}

function shortOptionTitle(title: string) {
  const t = title.replace(/\s*\(.*\)\s*$/, "").replace(/^По западной ветке\s+/i, "");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

function plural(n: number, one: string, few: string, many: string) {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

export function AlertModal({ alert, scenario, weather, shipments, nodes, busy, onAccept, onOther, onReject, onClose }: Props) {
  const best = alert.options.find((o) => o.recommended) ?? alert.options.find((o) => o.id !== "wait") ?? null;
  const lead = alert.starts_in_h != null ? Math.round(alert.starts_in_h) : stormLeadHours(alert, weather, scenario);
  const affected = alert.items
    .map((i) => shipments.find((s) => s.id === i.shipment_id))
    .filter((s): s is Shipment => !!s);
  const count = alert.items.length;
  // «По западной ветке через Самур и Астару (…)» → «Через Самур и Астару»: подпись плитки короткая.
  const bestTitle = shortOptionTitle(best?.title ?? "");

  return (
    <div
      role="dialog"
      aria-label="Прогноз шторма"
      data-map-ui
      className="absolute bottom-[96px] left-[22px] z-30 h-[371px] w-[632px] rounded-[12px] border border-[#FECACA] bg-panel px-[18px] shadow-[0_24px_60px_rgba(18,48,74,0.16)]"
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="Закрыть"
        className="absolute top-[17px] right-[18px] flex size-[36px] items-center justify-center rounded-[8px] border border-line bg-panel text-muted hover:bg-tile"
      >
        <CloseIcon size={16} />
      </button>

      <div className="flex pt-[17px]">
        <span className="flex size-[38px] shrink-0 items-center justify-center rounded-[10px] bg-risk-soft text-risk-text">
          <StormIcon size={18} />
        </span>
        <div className="caps mt-[2px] ml-[13px] text-[10.5px] leading-[13px] font-bold text-risk-text">
          Прогноз шторма{lead !== null && <> &nbsp;/&nbsp; через {lead}&nbsp;ч</>}
        </div>
      </div>

      <h2 className="mt-[13px] pr-[40px] text-[26px] whitespace-pre-line leading-[32px] font-bold">{headline(alert, scenario, weather, nodes)}</h2>
      <p className="mt-[10px] truncate text-[11px] leading-[14px] text-muted">
        Под риском {count}&nbsp;{plural(count, "груз", "груза", "грузов")}
        {affected.map((s) => ` · ${shipmentNumber(s.id)} ${s.title}`).join("")}
      </p>

      <div className="mt-[17px] flex gap-[7px]">
        <div className="h-[111px] flex-1 rounded-[12px] border border-[#FECACA] bg-risk-soft px-[13px] pt-[10px]">
          <div className="text-[12.5px] leading-[20px] font-bold text-risk-text">Ничего не делать</div>
          <div className="tnum mt-[10px] text-[32px] leading-[36px] font-bold">{formatHoursDelta(alert.do_nothing.delay_hours)}</div>
          <div className="mt-[9px] text-[11px] leading-[13px] text-muted">Простой {formatRub(alert.do_nothing.loss_rub)}</div>
        </div>
        <div className="h-[111px] flex-1 rounded-[12px] border border-[#BBF7D0] bg-ok-soft px-[13px] pt-[10px]">
          <div className="text-[12.5px] leading-[20px] font-bold text-ok">Решение диспетчера</div>
          {best ? (
            <>
              <div className="tnum mt-[10px] text-[32px] leading-[36px] font-bold">{formatHoursDelta(best.delay_vs_plan_h)}</div>
              <div className="mt-[9px] text-[11px] leading-[13px] text-muted">
                {bestTitle} · {formatSignedPct(alert.totals.co2_delta_pct)}&nbsp;CO₂
              </div>
            </>
          ) : (
            <div className="mt-[14px] text-[13px] leading-[18px] text-muted">Обхода нет — лучший вариант ждать следующий рейс.</div>
          )}
        </div>
      </div>

      <div className="mt-[24px] flex items-center gap-[11px]">
        {best && (
          <button
            type="button"
            disabled={busy}
            onClick={onAccept}
            className="flex h-[38px] w-[179px] items-center justify-center gap-[9px] rounded-[8px] bg-action text-[13px] font-bold text-white transition-colors hover:bg-action-hover disabled:opacity-60"
          >
            <CheckIcon size={14} strokeWidth={2} className="text-white/90" />
            Принять
          </button>
        )}
        <button
          type="button"
          onClick={onOther}
          className="h-[38px] w-[169px] rounded-[8px] border border-line-strong bg-panel text-[13px] font-bold transition-colors hover:bg-tile"
        >
          Другие варианты
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onReject}
          className="h-[38px] rounded-[9px] px-[16px] text-[13px] font-bold transition-colors hover:bg-tile disabled:opacity-60"
        >
          Отклонить
        </button>
      </div>
    </div>
  );
}
