"use client";

import { useMemo, useState } from "react";
import { cargoIcon } from "@/lib/derive";
import { formatDateTime, formatPercent, shipmentNumber, shortNodeName } from "@/lib/format";
import type { GraphNode, Shipment } from "@/lib/types";
import { FileIcon, FilterIcon, MapIcon, SearchIcon, TransportIcon } from "./icons";
import { StatusChip } from "./StatusChip";

interface Props {
  shipments: Shipment[];
  nodes: Map<string, GraphNode>;
  selectedId: string | null;
  view: "map" | "ledger";
  onSelect(id: string): void;
  onView(view: "map" | "ledger"): void;
}

function nodeName(nodes: Map<string, GraphNode>, id: string) {
  const n = nodes.get(id);
  return n ? shortNodeName(n.name) : id;
}

function ShipmentCard({
  s,
  nodes,
  selected,
  onSelect,
}: {
  s: Shipment;
  nodes: Map<string, GraphNode>;
  selected: boolean;
  onSelect(): void;
}) {
  const atRisk = s.display_status === "at_risk";
  const rerouted = s.display_status === "rerouted";
  const border = selected ? "#2C517B" : atRisk ? "#573244" : rerouted ? "#1E4A3A" : "#24304A";
  const tile = atRisk ? "rgba(239,68,68,0.15)" : rerouted ? "rgba(34,197,94,0.12)" : "#172338";
  const iconColor = atRisk ? "#FF888D" : rerouted ? "#7EE2A2" : "#9DC8FF";
  const prob = s.risk?.miss_probability ?? 0;

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className="block h-[90px] w-full shrink-0 rounded-[12px] border pt-[10px] pr-[13px] pl-[11px] text-left transition-colors hover:brightness-110"
      style={{ borderColor: border, background: selected ? "#192B45" : "#131C2E" }}
    >
      <div className="flex gap-[8px]">
        <span className="flex size-[34px] shrink-0 items-center justify-center rounded-[8px]" style={{ background: tile, color: iconColor }}>
          <TransportIcon kind={cargoIcon(s)} size={16} />
        </span>
        <div className="min-w-0 pt-[1px]">
          <div className="truncate text-[15px] leading-[18px] font-bold">
            <span className="tnum">{shipmentNumber(s.id)}</span>
            <span className="ml-[7px]">{s.title}</span>
          </div>
          <div className="mt-[3px] truncate text-[11.5px] leading-[14px] text-muted">
            {nodeName(nodes, s.origin)} → {nodeName(nodes, s.destination)}
          </div>
        </div>
      </div>
      <div className="mt-[15px] flex items-center pl-[1px]">
        <StatusChip status={s.display_status} />
        <span className="tnum ml-auto text-[11px] text-faint">{formatDateTime(s.eta)}</span>
        <span
          className="tnum w-[44px] text-right text-[14px] leading-none font-bold"
          style={{ color: s.risk_level === "high" ? "#FF888D" : s.risk_level === "medium" ? "#F5A524" : "#8A97AD" }}
        >
          {formatPercent(prob)}
        </span>
      </div>
    </button>
  );
}

export function ShipmentList({ shipments, nodes, selectedId, view, onSelect, onView }: Props) {
  const [query, setQuery] = useState("");
  const [onlyRisk, setOnlyRisk] = useState(false);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase().replace(/^№/, "");
    return shipments.filter((s) => {
      if (onlyRisk && s.display_status !== "at_risk") return false;
      if (!q) return true;
      const num = shipmentNumber(s.id).slice(1);
      return num.includes(q) || s.title.toLowerCase().includes(q) || s.id.includes(q);
    });
  }, [shipments, query, onlyRisk]);

  return (
    <aside className="flex w-[320px] shrink-0 flex-col bg-bg shadow-[inset_-1px_0_0_var(--color-line)]">
      <div className="mt-[23.5px] flex h-[35px] items-start justify-between pr-[21px] pl-5">
        <div className="flex items-start">
          <h1 className="text-[28px] leading-[34px] font-bold">Грузы</h1>
          <span className="tnum mt-[4.5px] -ml-[1px] flex h-[23px] min-w-[26px] items-center justify-center rounded-[7px] bg-tile px-[6px] text-[11px] font-bold text-transit-text">
            {shipments.length}
          </span>
        </div>
        <button
          type="button"
          onClick={() => setOnlyRisk((v) => !v)}
          aria-pressed={onlyRisk}
          title={onlyRisk ? "Показать все грузы" : "Только под риском"}
          className={`flex size-[35px] items-center justify-center rounded-[8px] border transition-colors ${
            onlyRisk ? "border-[#573244] bg-[#281D2B] text-risk-text" : "border-line-strong bg-panel text-[#CFD6E1] hover:bg-tile"
          }`}
        >
          <FilterIcon size={16} />
        </button>
      </div>

      <label className="mx-5 mt-[14px] flex h-[35px] items-center gap-[9px] rounded-[8px] border border-line bg-field px-[12px] text-muted focus-within:border-line-strong">
        <SearchIcon size={13} strokeWidth={1.8} />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Поиск по номеру или грузу"
          className="w-full bg-transparent text-[12.5px] text-text outline-none placeholder:text-muted"
        />
      </label>

      <div className="scroll-thin mt-[14px] flex min-h-0 flex-1 flex-col gap-[11px] overflow-y-auto px-5 pb-4">
        {visible.map((s) => (
          <ShipmentCard key={s.id} s={s} nodes={nodes} selected={s.id === selectedId} onSelect={() => onSelect(s.id)} />
        ))}
        {visible.length === 0 && <div className="pt-6 text-center text-[12.5px] text-muted">Ничего не найдено</div>}
      </div>

      <div className="mx-5 border-t border-line pt-[13px] pb-[27px]">
        <div className="caps text-[10.5px] leading-[12px] font-bold text-muted">Рабочая область</div>
        <div className="mt-[14px] flex h-[43px] items-center gap-[4px] rounded-[10px] border border-[#1A263B] bg-field p-[3px]">
          {(
            [
              ["map", "Карта", MapIcon],
              ["ledger", "Реестр", FileIcon],
            ] as const
          ).map(([key, title, Ico]) => {
            const active = view === key;
            return (
              <button
                key={key}
                type="button"
                aria-pressed={active}
                onClick={() => onView(key)}
                className={`flex h-[36px] flex-1 items-center justify-center gap-[9px] rounded-[8px] border text-[14px] font-bold transition-colors ${
                  active ? "border-[#2A3850] bg-tile" : "border-transparent hover:bg-tile/60"
                }`}
              >
                <Ico size={15} className="text-transit-text" />
                {title}
              </button>
            );
          })}
        </div>
      </div>
    </aside>
  );
}
