"use client";

import { formatDateTime, formatInt } from "@/lib/format";
import type { GraphNode, Sailing, Shipment } from "@/lib/types";
import { Empty, Pill, Row, SectionPage, Table, nodeName } from "./common";

const COLS = "minmax(150px,1fr) minmax(130px,1fr) minmax(130px,1fr) 136px 136px minmax(220px,1.6fr) 120px";
const STATUS: Record<Sailing["status"], { label: string; tone: "info" | "risk" | "muted" }> = {
  scheduled: { label: "По расписанию", tone: "info" },
  cancelled: { label: "Отменён", tone: "risk" },
  departed: { label: "Ушёл", tone: "muted" },
};

/** Полоса загрузки: занято из вместимости (booked_t / capacity_t с сервера). */
function LoadBar({ booked, capacity }: { booked: number; capacity: number }) {
  const share = capacity > 0 ? Math.min(1, booked / capacity) : 0;
  const tone = share >= 0.95 ? "var(--color-risk)" : share >= 0.8 ? "var(--color-warn)" : "var(--color-cyan)";
  return (
    <div className="min-w-0">
      <div className="h-[8px] overflow-hidden rounded-full bg-tile">
        <div className="h-full rounded-full" style={{ width: `${share * 100}%`, background: tone }} />
      </div>
      <div className="tnum mt-[6px] text-[13px] text-muted">
        {formatInt(booked)} из {formatInt(capacity)}&nbsp;т
      </div>
    </div>
  );
}

export function SailingsSection({ sailings, nodes, shipments }: { sailings: Sailing[]; nodes: Map<string, GraphNode>; shipments: Shipment[] }) {
  const sorted = [...sailings].sort((a, b) => Date.parse(a.departure) - Date.parse(b.departure));
  // Какие наши грузы стоят на рейсе — по sailing_id этапов их текущих маршрутов.
  const onBoard = new Map<string, string[]>();
  for (const s of shipments) {
    for (const leg of s.route.legs) {
      if (leg.sailing_id && leg.status !== "done") onBoard.set(leg.sailing_id, [...(onBoard.get(leg.sailing_id) ?? []), s.id]);
    }
  }
  return (
    <SectionPage kicker="Расписание / Паромы Каспия" title="Рейсы" subtitle="Расписание и загрузка портов — демо-данные">
      <Table cols={COLS} head={["Рейс", "Откуда", "Куда", "Отправление", "Окончание приёма", "Загрузка", "Статус"]} minWidth={1080}>
        {sorted.length === 0 && <Empty>Рейсов нет</Empty>}
        {sorted.map((s) => {
          const st = STATUS[s.status];
          const ours = onBoard.get(s.id) ?? [];
          return (
            <Row key={s.id} cols={COLS}>
              <span className="min-w-0">
                <span className="block truncate font-bold">{s.id}</span>
                {ours.length > 0 && <span className="block truncate text-[13px] text-muted">наших грузов: {ours.length}</span>}
              </span>
              <span className="truncate">{nodeName(nodes, s.from)}</span>
              <span className="truncate">{nodeName(nodes, s.to)}</span>
              <span className="tnum text-[14px]">{formatDateTime(s.departure)}</span>
              <span className="tnum text-[14px] text-muted">{formatDateTime(s.cutoff)}</span>
              <LoadBar booked={s.booked_t} capacity={s.capacity_t} />
              <span title={s.cancel_reason ?? undefined}>
                <Pill tone={st.tone}>{st.label}</Pill>
              </span>
            </Row>
          );
        })}
      </Table>
    </SectionPage>
  );
}
