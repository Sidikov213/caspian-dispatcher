"use client";

import { ROLE_LABEL } from "@/lib/session";
import { formatDateTime, formatInt, formatRub, shipmentNumber } from "@/lib/format";
import type { Alert } from "@/lib/types";
import { Empty, Pill, Row, SectionPage, Table, VIA_LABEL } from "./common";

const COLS = "minmax(200px,1.4fr) 104px minmax(180px,1.3fr) minmax(180px,1.3fr) minmax(160px,1fr) 160px";

const STATUS: Record<Alert["status"], { label: string; tone: "info" | "ok" | "muted" | "warn" }> = {
  new: { label: "Ждёт решения", tone: "info" },
  accepted: { label: "Принято", tone: "ok" },
  rejected: { label: "Отклонено", tone: "warn" },
  superseded: { label: "Закрыто", tone: "muted" },
};

const cut = (t: string) => t.replace(/\s*\(.*\)\s*$/, "");

/** Что принято: у принятого алерта рекомендованным помечен принятый вариант (контракт Alert.options). */
function decided(a: Alert): string {
  if (a.status === "accepted") return cut(a.options.find((o) => o.recommended)?.title ?? "Ждать следующий рейс");
  if (a.status === "rejected") return "Ждать следующий рейс";
  if (a.status === "superseded") return a.status_note ?? "Предложение устарело";
  return "—";
}

/** Кто принял: имя и роль из accepted_by, если есть; иначе только «через сайт / через Telegram». */
function who(a: Alert): { name: string | null; via: string } {
  if (a.status !== "accepted") return { name: null, via: "—" };
  const via = a.accepted_via ? VIA_LABEL[a.accepted_via] : "—";
  return { name: a.accepted_by ? `${a.accepted_by.name} · ${ROLE_LABEL[a.accepted_by.role]}` : null, via };
}

export function DecisionsSection({ alerts }: { alerts: Alert[] }) {
  const sorted = [...alerts].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || b.id.localeCompare(a.id));
  return (
    <SectionPage
      kicker="ИИ-диспетчер / История"
      title="Решения"
      subtitle="Угроза, предложение диспетчера и что выбрал человек. Деньги и часы — расчётные"
    >
      <Table cols={COLS} head={["Угроза", "Источник", "Предложено", "Принято", "Кем и откуда", "Расчётная экономия"]} minWidth={1120}>
        {sorted.length === 0 && <Empty>Решений пока нет. Алерты появляются, когда диспетчер видит угрозу на 48 ч вперёд</Empty>}
        {sorted.map((a) => {
          const st = STATUS[a.status];
          const offered = a.options.filter((o) => o.id !== "wait");
          return (
            <Row key={a.id} cols={COLS}>
              <span className="min-w-0">
                <span className="block truncate font-bold" title={a.title}>
                  {a.title}
                </span>
                <span className="mt-[2px] block truncate text-[13px] text-muted">
                  {formatDateTime(a.created_at)} · {a.items.map((i) => shipmentNumber(i.shipment_id)).join(", ") || "грузов нет"}
                </span>
              </span>
              <span>
                {a.source ? <Pill tone={a.source === "forecast" ? "info" : "muted"}>{a.source === "forecast" ? "Прогноз" : "Сценарий"}</Pill> : "—"}
              </span>
              <span className="min-w-0 text-[14px]">
                {offered.length === 0 ? (
                  <span className="text-muted">Обхода нет — ждать рейс</span>
                ) : (
                  offered.map((o) => (
                    <span key={o.id} className="block truncate" title={o.title}>
                      {cut(o.title)}
                    </span>
                  ))
                )}
              </span>
              <span className="min-w-0">
                <span className="block">
                  <Pill tone={st.tone}>{st.label}</Pill>
                </span>
                <span className="mt-[4px] block truncate text-[14px]" title={decided(a)}>
                  {decided(a)}
                </span>
              </span>
              <span className="min-w-0 text-[14px]">
                {who(a).name && (
                  <span className="block truncate font-bold" title={who(a).name ?? undefined}>
                    {who(a).name}
                  </span>
                )}
                <span className="block truncate">{who(a).via}</span>
                {a.accepted_at && <span className="tnum block text-[13px] text-muted">{formatDateTime(a.accepted_at)}</span>}
              </span>
              <span className={a.status === "accepted" ? "font-bold text-rerouted-text" : "text-muted"}>
                <span className="tnum block">{formatRub(a.totals.saved_rub)}</span>
                <span className="tnum block text-[13px] font-normal text-muted">{formatInt(a.totals.saved_hours)} груз-ч</span>
              </span>
            </Row>
          );
        })}
      </Table>
    </SectionPage>
  );
}
