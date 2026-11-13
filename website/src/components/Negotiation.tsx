"use client";

import { useEffect, useRef, useState } from "react";
import { formatDateTime } from "@/lib/format";
import type { AlertOption, NegotiationStep } from "@/lib/types";
import { CheckIcon } from "./icons";

/** Шаги согласования появляются по одному с этим интервалом. */
const STEP_MS = 700;

const ACTOR_LABEL: Record<NegotiationStep["actor"], string> = {
  ferry: "Паром",
  port: "Порт",
  customs: "Таможня",
  rail: "Ж/д",
};

const RESULT: Record<NegotiationStep["result"], { label: string; text: string; bg: string; line: string }> = {
  ok: { label: "Подтверждено", text: "var(--color-ok)", bg: "var(--color-ok-soft)", line: "var(--color-ok-line)" },
  reject: { label: "Отказ", text: "var(--color-risk-text)", bg: "var(--color-risk-soft)", line: "var(--color-risk-line)" },
  counter: { label: "Встречное", text: "var(--color-warn-text)", bg: "var(--color-warn-soft)", line: "var(--color-warn-line)" },
};

function stepsWord(n: number) {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return "шаг";
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "шага";
  return "шагов";
}

/** Согласовано: последний ответ каждого участника — «подтверждено». */
function agreed(steps: NegotiationStep[]) {
  const last = new Map<string, string>();
  for (const s of steps) last.set(s.actor, s.result);
  return steps.length > 0 && [...last.values()].every((r) => r === "ok");
}

/**
 * Блок «Согласование» в карточке алерта: шаги из Alert.negotiation, по одному раз в 0,7 с.
 * Участники — цифровые модели (детерминированный код на сервере), каждый шаг записан в журнал.
 * Компонент монтируется с key = id алерта, поэтому показ начинается заново для нового алерта.
 */
export function NegotiationBlock({ steps }: { steps: NegotiationStep[] }) {
  const [shown, setShown] = useState(1);
  const lastRef = useRef<HTMLLIElement>(null);
  const total = steps.length;

  useEffect(() => {
    if (shown >= total) return;
    const t = window.setTimeout(() => setShown((n) => Math.min(n + 1, total)), STEP_MS);
    return () => window.clearTimeout(t);
  }, [shown, total]);

  // Новый шаг докручивается в видимую часть карточки (она прокручивается, когда выше экрана).
  useEffect(() => {
    if (shown > 1) lastRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [shown]);

  if (total === 0) return null;
  const done = shown >= total;
  const ok = agreed(steps);

  return (
    <section aria-label="Согласование" className="mt-[14px] rounded-[12px] border border-line bg-tile px-[13px] pt-[10px] pb-[9px]">
      <div className="flex items-baseline justify-between gap-[10px]">
        <div className="caps text-[10.5px] font-bold text-muted">Согласование</div>
        <div
          aria-live="polite"
          className="tnum flex items-center gap-[5px] text-[12px] font-bold"
          style={{ color: !done ? "var(--color-muted)" : ok ? "var(--color-ok)" : "var(--color-risk-text)" }}
        >
          {done && ok && (
            <span aria-hidden className="negotiation-done flex">
              <CheckIcon size={13} strokeWidth={2.6} />
            </span>
          )}
          {!done
            ? `Шаг ${shown} из ${total}…`
            : ok
              ? `Согласовано за ${total} ${stepsWord(total)}`
              : `Не согласовано: ${total} ${stepsWord(total)}`}
        </div>
      </div>
      <div className="mt-[2px] text-[10.5px] leading-[13px] text-muted">
        Цифровые модели участников · каждый шаг — запись в проверяемом журнале
      </div>
      <ol className="mt-[8px] space-y-[5px]">
        {steps.slice(0, shown).map((s, i) => {
          const r = RESULT[s.result];
          return (
            <li
              key={i}
              ref={i === shown - 1 ? lastRef : undefined}
              className="negotiation-step flex scroll-mb-[150px] items-start gap-[9px]"
              title={s.detail}
            >
              <span className="mt-px w-[62px] shrink-0 rounded-[6px] border border-line bg-panel py-[2px] text-center text-[10.5px] leading-[14px] font-bold">
                {ACTOR_LABEL[s.actor] ?? s.actor}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12px] leading-[18px] font-semibold">{s.action}</span>
                {s.result !== "ok" && <span className="block text-[11px] leading-[14px] text-muted">{s.detail}</span>}
              </span>
              <span
                className="mt-px shrink-0 rounded-[6px] border px-[7px] py-[2px] text-[10.5px] leading-[14px] font-bold"
                style={{ color: r.text, background: r.bg, borderColor: r.line }}
              >
                {r.label}
                {s.block_index != null && <span className="ml-[5px] font-medium opacity-70">№{s.block_index + 1}</span>}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/** Текущее время, обновляется раз в секунду: таймеру «окна спасения» хватает. */
function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  return now;
}

/** Вариант недоступен: сервер пометил available: false или срок decide_by уже прошёл. */
export function optionExpired(o: Pick<AlertOption, "decide_by" | "available"> | null | undefined, now: number): boolean {
  if (!o) return false;
  if (o.available === false) return true;
  return !!o.decide_by && now > Date.parse(o.decide_by);
}

/** Часы для проверки сроков вариантов — те же, что у таймера. */
export function useDeadlineClock(): number {
  return useNow();
}

/** «Окно спасения»: сколько ещё можно принимать вариант (Alert.decide_by / AlertOption.decide_by). */
export function RescueWindow({ decideBy, expired, now }: { decideBy: string; expired: boolean; now: number }) {
  const left = Math.max(0, Date.parse(decideBy) - now);
  const h = Math.floor(left / 3_600_000);
  const m = Math.floor((left % 3_600_000) / 60_000);
  const soon = !expired && left < 3 * 3_600_000;
  return (
    <div
      role="timer"
      className="mt-[14px] flex items-center justify-between gap-[10px] rounded-[10px] border px-[13px] py-[8px]"
      style={
        expired
          ? { borderColor: "var(--color-line)", background: "var(--color-tile)", color: "var(--color-muted)" }
          : soon
            ? { borderColor: "var(--color-warn-line)", background: "var(--color-warn-soft)" }
            : { borderColor: "var(--color-line)", background: "var(--color-info-soft)" }
      }
    >
      <div className="min-w-0">
        <div className="caps text-[10px] font-bold text-muted">Окно спасения</div>
        <div className="tnum mt-[2px] truncate text-[13px] leading-[17px] font-bold">
          {expired
            ? "Срок решения истёк: вариант недоступен"
            : `Решение можно принять ещё ${h} ч ${m} мин`}
        </div>
      </div>
      <div className="tnum shrink-0 text-right text-[11px] leading-[14px] text-muted">
        {expired ? "закрыто" : "до"} {formatDateTime(decideBy)}
      </div>
    </div>
  );
}
