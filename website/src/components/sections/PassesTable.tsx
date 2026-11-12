"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { checkpointLabel } from "@/lib/derive";
import { formatDateTime, shipmentNumber } from "@/lib/format";
import type { GraphNode, Pass, Shipment } from "@/lib/types";
import { PassModal } from "../PassModal";
import { Empty, Pill, Row, Table } from "./common";

const COLS = "120px minmax(180px,1.4fr) minmax(170px,1.2fr) 150px 140px 150px";
const STATUS: Record<Pass["status"], { label: string; tone: "ok" | "muted" | "risk" }> = {
  active: { label: "Действует", tone: "ok" },
  reissued: { label: "Переоформлен", tone: "muted" },
  revoked: { label: "Отозван", tone: "risk" },
};

/** Все пропуска из GET /api/passes (новые сверху), перезапрос при новой записи в реестре. */
export function PassesTable({ version, shipments, nodes }: { version: string; shipments: Shipment[]; nodes: Map<string, GraphNode> }) {
  const [passes, setPasses] = useState<Pass[] | null>(null);
  const [open, setOpen] = useState<Pass | null>(null);
  useEffect(() => {
    let cancelled = false;
    api.getPasses().then((p) => !cancelled && setPasses(p), () => !cancelled && setPasses([]));
    return () => {
      cancelled = true;
    };
  }, [version]);
  const byId = new Map(shipments.map((s) => [s.id, s]));
  const openShipment = open ? byId.get(open.shipment_id) : undefined;

  return (
    <section className="mt-[32px]">
      <h2 className="text-[22px] leading-[28px] font-bold">Пропуска</h2>
      <p className="mt-[4px] mb-[16px] text-[15px] text-muted">Все выпущенные, включая переоформленные. Клик — QR и проверка</p>
      <Table cols={COLS} head={["Пропуск", "Груз", "Пункт пропуска", "Действует до", "Статус", "Запись в реестре"]} minWidth={1000}>
        {passes === null && <Empty>Загружаем…</Empty>}
        {passes?.length === 0 && <Empty>Пропусков пока нет</Empty>}
        {passes?.map((p) => {
          const s = byId.get(p.shipment_id);
          const st = STATUS[p.status];
          return (
            <Row key={p.id} cols={COLS} onClick={s ? () => setOpen(p) : undefined}>
              <span className="tnum truncate font-bold">{p.id}</span>
              <span className="truncate">{s ? `${shipmentNumber(s.id)} ${s.title}` : shipmentNumber(p.shipment_id)}</span>
              <span className="truncate">{checkpointLabel(nodes.get(p.checkpoint_node), p.checkpoint_node)}</span>
              <span className="tnum text-[14px]">{formatDateTime(p.valid_until)}</span>
              <span>
                <Pill tone={st.tone}>{st.label}</Pill>
              </span>
              <span className="tnum truncate text-[13px] text-transit-text" title={p.block_hash}>
                {p.block_hash.slice(0, 4)}…{p.block_hash.slice(-4)}
              </span>
            </Row>
          );
        })}
      </Table>
      {open && openShipment && <PassModal pass={open} shipment={openShipment} nodes={nodes} onClose={() => setOpen(null)} />}
    </section>
  );
}
