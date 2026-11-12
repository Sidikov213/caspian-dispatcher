"use client";

import { useState } from "react";
import { formatInt, shipmentNumber, formatHoursDelta, formatRub, formatSignedPct, shortNodeName } from "@/lib/format";
import { stormLeadHours, stormScope } from "@/lib/derive";
import type { Alert, GraphNode, Scenario, Shipment, Weather } from "@/lib/types";
import { AlertDecisionNote } from "./AlertDecisionNote";
import { CheckIcon, CloseIcon, HazardIcon } from "./icons";
import { NegotiationBlock, RescueWindow, optionExpired, useDeadlineClock } from "./Negotiation";

interface Props {
  alert: Alert;
  scenario: Scenario | null;
  weather: Weather | null;
  shipments: Shipment[];
  nodes: Map<string, GraphNode>;
  busy: boolean;
  /** Право decide_alert: без него вместо кнопок — «Решение принимает логист». */
  canDecide: boolean;
  /** Принять выбранный вариант из Alert.options. */
  onAccept(optionId: string): void;
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
  const hz = alert.hazard ?? scenario?.hazard ?? scenario?.type ?? "storm";
  if (hz === "storm" && stormScope(weather) === "full") return "Шторм остановит паромы\nна всём Каспии";
  const blocked = alert.items.flatMap((i) => i.from_route?.legs ?? []).find((l) => l.status === "blocked");
  if (!blocked || (hz !== "storm" && hz !== "ice")) return alert.card?.headline ?? alert.title;
  const what = hz === "ice" ? "Лёд закроет" : "Шторм закроет";
  return `${what} ${blocked.mode === "sea" ? "переправу" : "участок"}\n${name(nodes, blocked.from)} — ${name(nodes, blocked.to)}`;
}

/** Подзаголовок угрозы над заголовком. */
function kicker(hz: string): string {
  if (hz === "ice") return "Ледовая обстановка";
  if (hz === "storm") return "Прогноз шторма";
  return "Угроза";
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

export function AlertModal({ alert, scenario, weather, shipments, nodes, busy, canDecide, onAccept, onOther, onReject, onClose }: Props) {
  // Варианты — прямо из Alert.options (рекомендованный первый); «ждать» — это «Отклонить».
  const choices = alert.options.filter((o) => o.id !== "wait");
  const [picked, setPicked] = useState<string | null>(null);
  const best = choices.find((o) => o.id === picked) ?? choices.find((o) => o.recommended) ?? choices[0] ?? null;
  const hz = alert.hazard ?? scenario?.hazard ?? scenario?.type ?? "storm";
  const lead = alert.starts_in_h != null ? Math.round(alert.starts_in_h) : stormLeadHours(alert, weather, scenario);
  const affected = alert.items
    .map((i) => shipments.find((s) => s.id === i.shipment_id))
    .filter((s): s is Shipment => !!s);
  const count = alert.items.length;
  // «По западной ветке через Самур и Астару (…)» → «Через Самур и Астару»: подпись плитки короткая.
  const bestTitle = shortOptionTitle(best?.title ?? "");
  // «Окно спасения»: после decide_by вариант серый, «Принять» недоступна (сервер ответит 409).
  const now = useDeadlineClock();
  const bestExpired = optionExpired(best, now);

  return (
    <div
      role="dialog"
      aria-label="Прогноз шторма"
      data-map-ui
      className="absolute bottom-[96px] left-[22px] z-30 max-h-[calc(100%-112px)] w-[632px] overflow-y-auto rounded-[12px] border border-[var(--color-risk-line)] bg-panel px-[18px] shadow-[0_24px_60px_var(--color-shadow)]"
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
          <HazardIcon hazard={hz} size={18} />
        </span>
        <div className="caps mt-[2px] ml-[13px] text-[10.5px] leading-[13px] font-bold text-risk-text">
          {kicker(hz)}
          {lead !== null && <> &nbsp;/&nbsp; через {lead}&nbsp;ч</>}
          {alert.source && <> &nbsp;/&nbsp; {alert.source === "forecast" ? "найдено в прогнозе" : "сценарий"}</>}
        </div>
      </div>

      <h2 className="mt-[13px] pr-[40px] text-[26px] whitespace-pre-line leading-[32px] font-bold">{headline(alert, scenario, weather, nodes)}</h2>
      <p className="mt-[10px] truncate text-[11px] leading-[14px] text-muted">
        Под риском {count}&nbsp;{plural(count, "груз", "груза", "грузов")}
        {affected.map((s) => ` · ${shipmentNumber(s.id)} ${s.title}`).join("")}
      </p>
      {alert.card && (
        <div className="mt-[10px] flex flex-wrap gap-[6px]">
          {alert.card.period && (
            <span className="rounded-[6px] bg-tile px-[8px] py-[3px] text-[11.5px] text-muted">{alert.card.period}</span>
          )}
          {alert.card.metrics.map((m) => (
            <span key={m.key} className="rounded-[6px] bg-tile px-[8px] py-[3px] text-[11.5px]">
              <span className="text-muted">{m.label}:</span> <b>{m.value}</b>
            </span>
          ))}
        </div>
      )}
      {alert.card?.note && <p className="mt-[8px] text-[11.5px] font-semibold text-warn-text">{alert.card.note}</p>}

      <div className="mt-[17px] flex gap-[7px]">
        <div className="h-[111px] min-w-0 flex-1 rounded-[12px] border border-[var(--color-risk-line)] bg-risk-soft px-[13px] pt-[10px]">
          <div className="text-[12.5px] leading-[20px] font-bold text-risk-text">Ничего не делать</div>
          <div className="tnum mt-[10px] text-[32px] leading-[36px] font-bold">{formatHoursDelta(alert.do_nothing.delay_hours)}</div>
          <div className="mt-[9px] text-[11px] leading-[13px] text-muted">Простой {formatRub(alert.do_nothing.loss_rub)}</div>
        </div>
        <div className="h-[111px] min-w-0 flex-1 rounded-[12px] border border-[var(--color-ok-line)] bg-ok-soft px-[13px] pt-[10px]">
          <div className="text-[12.5px] leading-[20px] font-bold text-ok">Решение диспетчера</div>
          {best ? (
            <>
              <div className="tnum mt-[10px] text-[32px] leading-[36px] font-bold">{formatHoursDelta(best.delay_vs_plan_h)}</div>
              <div className="mt-[9px] truncate text-[11px] leading-[13px] text-muted">
                {bestTitle} · {formatRub(best.saved_rub)} · {best.recommended ? `${formatSignedPct(alert.totals.co2_delta_pct)}\u00A0CO₂` : `${best.co2_delta_kg > 0 ? "+" : ""}${formatInt(best.co2_delta_kg)}\u00A0кг CO₂`}
              </div>
            </>
          ) : (
            <div className="mt-[14px] text-[13px] leading-[18px] text-muted">Обхода нет — лучший вариант ждать следующий рейс.</div>
          )}
        </div>
      </div>

      {choices.length > 1 && (
        <div className="mt-[14px] flex flex-wrap gap-[8px]" role="radiogroup" aria-label="Вариант решения">
          {choices.map((o) => {
            const on = o.id === best?.id;
            const gone = optionExpired(o, now);
            return (
              <button
                key={o.id}
                type="button"
                role="radio"
                aria-checked={on}
                aria-disabled={gone}
                title={gone ? "Срок решения истёк: вариант недоступен" : o.title}
                onClick={() => setPicked(o.id)}
                className={`min-h-[34px] max-w-full rounded-[8px] border px-[12px] py-[6px] text-left text-[12.5px] leading-[18px] font-bold transition-colors ${
                  gone
                    ? "border-line bg-tile text-faint line-through decoration-1"
                    : on
                      ? "border-action bg-info-soft text-text"
                      : "border-line text-muted hover:bg-tile"
                }`}
              >
                {shortOptionTitle(o.title)} · {formatHoursDelta(o.delay_vs_plan_h)}
                {o.recommended && !gone && <span className="ml-[6px] text-rerouted-text">рекомендуем</span>}
              </button>
            );
          })}
        </div>
      )}

      {alert.negotiation && alert.negotiation.length > 0 && <NegotiationBlock key={alert.id} steps={alert.negotiation} />}

      {!canDecide && (
        <div className="mt-[18px]">
          <AlertDecisionNote alert={alert} />
        </div>
      )}

      {/* Таймер и кнопки решения всегда видны: карточка с согласованием может быть выше экрана и прокручивается. */}
      <div className="sticky bottom-0 z-10 -mx-[18px] mt-[4px] bg-panel px-[18px] pb-[18px]">
      {best?.decide_by && <RescueWindow decideBy={best.decide_by} expired={bestExpired} now={now} />}
      <div className="flex items-center gap-[11px] pt-[14px]">
        {canDecide && best && (
          <button
            type="button"
            disabled={busy || bestExpired}
            title={bestExpired ? "Срок решения истёк: вариант недоступен" : undefined}
            onClick={() => onAccept(best.id)}
            className="flex h-[38px] w-[179px] items-center justify-center gap-[9px] rounded-[8px] bg-action text-[13px] font-bold text-white transition-colors hover:bg-action-hover disabled:cursor-not-allowed disabled:bg-[var(--color-line-strong)] disabled:text-muted disabled:opacity-60"
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
          {canDecide ? "Другие варианты" : "Подробнее"}
        </button>
        {canDecide && (
          <button
            type="button"
            disabled={busy}
            onClick={onReject}
            className="h-[38px] rounded-[9px] px-[16px] text-[13px] font-bold transition-colors hover:bg-tile disabled:opacity-60"
          >
            Отклонить
          </button>
        )}
      </div>
      </div>
    </div>
  );
}
