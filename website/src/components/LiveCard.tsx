"use client";

import { formatDateTime, formatPercent, formatInt, shipmentNumber, shortNodeName } from "@/lib/format";
import type { GraphNode, Mode, Shipment } from "@/lib/types";
import { StatusChip } from "./StatusChip";
import { CloseIcon, RailIcon, RoadIcon, SeaIcon } from "./icons";

export const MODE_LABEL: Record<Mode, string> = { rail: "Ж/д", road: "Авто", sea: "Море" };
const MODE_ICON: Record<Mode, typeof RailIcon> = { rail: RailIcon, road: RoadIcon, sea: SeaIcon };

const box =
  "absolute top-[76px] left-5 z-[600] w-[340px] rounded-[12px] border border-line bg-panel p-[16px] shadow-[0_16px_40px_var(--color-shadow)]";
const closeBtn =
  "absolute top-[12px] right-[12px] flex size-[32px] items-center justify-center rounded-[8px] border border-line text-muted hover:bg-tile";

const name = (nodes: Map<string, GraphNode>, id: string | undefined) => (id ? shortNodeName(nodes.get(id)?.name ?? id) : "—");

/** Карточка груза по клику на значок: всё из Shipment и Shipment.position, клиент ничего не считает. */
export function LiveCard({
  shipment: s,
  nodes,
  onOpen,
  onClose,
}: {
  shipment: Shipment;
  nodes: Map<string, GraphNode>;
  onOpen(): void;
  onClose(): void;
}) {
  const p = s.position;
  const Icon = p ? MODE_ICON[p.mode] : null;
  const row = "flex justify-between gap-[12px] py-[5px] text-[14px]";
  return (
    <div data-map-ui className={box} role="dialog" aria-label={`Груз ${shipmentNumber(s.id)}`}>
      <button type="button" onClick={onClose} aria-label="Закрыть" className={closeBtn}>
        <CloseIcon size={14} />
      </button>
      <div className="flex items-center gap-[8px]">
        <span className="tnum text-[13px] font-bold text-muted">{shipmentNumber(s.id)}</span>
        <StatusChip status={s.display_status} />
      </div>
      <h3 className="mt-[4px] pr-[40px] text-[19px] leading-[25px] font-bold">{s.title}</h3>
      <div className="mt-[10px] divide-y divide-line">
        <div className={row}>
          <span className="text-muted">Вес</span>
          <span className="tnum font-bold">{formatInt(s.weight_t)} т</span>
        </div>
        {p && Icon && (
          <div className={row}>
            <span className="text-muted">Транспорт</span>
            <span className="flex items-center gap-[6px] font-bold">
              <Icon size={15} />
              {MODE_LABEL[p.mode]}
              {p.waiting && p.waiting_label && <span className="font-normal text-warn-text">· {p.waiting_label}</span>}
            </span>
          </div>
        )}
        {p && (
          <div className={row}>
            <span className="text-muted">Участок</span>
            <span className="text-right font-bold">
              {name(nodes, p.from_node)} → {name(nodes, p.to_node)}
            </span>
          </div>
        )}
        {p && (
          <div className={row}>
            <span className="text-muted">{p.waiting ? "Прибытие после рейса" : `Прибытие в ${name(nodes, p.to_node)}`}</span>
            <span className="tnum font-bold">{formatDateTime(p.eta_next_node)}</span>
          </div>
        )}
        <div className={row}>
          <span className="text-muted">Конечная · {name(nodes, s.destination)}</span>
          <span className="tnum font-bold">{formatDateTime(s.eta)}</span>
        </div>
        {s.risk && (
          <div className={row}>
            <span className="text-muted">Риск срыва стыковки</span>
            <span className={`tnum font-bold ${s.risk_level === "high" ? "text-risk-text" : ""}`}>{formatPercent(s.risk.miss_probability)}</span>
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={onOpen}
        className="mt-[12px] h-[40px] w-full rounded-[10px] bg-action text-[14px] font-bold text-white hover:bg-action-hover"
      >
        Открыть груз
      </button>
    </div>
  );
}

/** Несколько грузов в одной точке: список, клик — карточка груза. */
export function LiveList({
  shipments,
  onPick,
  onClose,
}: {
  shipments: Shipment[];
  onPick(id: string): void;
  onClose(): void;
}) {
  return (
    <div data-map-ui className={box} role="dialog" aria-label="Грузы в этой точке">
      <button type="button" onClick={onClose} aria-label="Закрыть" className={closeBtn}>
        <CloseIcon size={14} />
      </button>
      <div className="caps text-[10px] font-bold text-muted">В этой точке</div>
      <h3 className="mt-[4px] text-[19px] leading-[25px] font-bold">
        {shipments.length} {shipments.length % 10 >= 2 && shipments.length % 10 <= 4 && (shipments.length % 100 < 12 || shipments.length % 100 > 14) ? "груза" : "грузов"}
      </h3>
      <ul className="mt-[8px] divide-y divide-line">
        {shipments.map((s) => (
          <li key={s.id}>
            <button type="button" onClick={() => onPick(s.id)} className="flex w-full items-center gap-[8px] py-[8px] text-left text-[14px] hover:text-transit-text">
              <span className="tnum w-[34px] font-bold text-muted">{shipmentNumber(s.id)}</span>
              <span className="flex-1 truncate font-bold">{s.title}</span>
              <StatusChip status={s.display_status} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
