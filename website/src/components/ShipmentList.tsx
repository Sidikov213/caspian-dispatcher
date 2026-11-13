"use client";

import { useEffect, useMemo, useState } from "react";
import { cargoIcon } from "@/lib/derive";
import { formatDateTime, formatPercent, shipmentNumber, shortNodeName } from "@/lib/format";
import type { GraphNode, Shipment } from "@/lib/types";
import { FilterIcon, SearchIcon, TransportIcon } from "./icons";
import { StatusChip } from "./StatusChip";

interface Props {
  shipments: Shipment[];
  nodes: Map<string, GraphNode>;
  selectedId: string | null;
  onSelect(id: string): void;
}

function nodeName(nodes: Map<string, GraphNode>, id: string) {
  const n = nodes.get(id);
  return n ? shortNodeName(n.name) : id;
}

/** Грузы, у которых подсветка «стал под риском» уже отыграла: при возврате на пульт она не повторяется. */
const riskFlashed = new Set<string>();
const RISK_FLASH_MS = 1400;

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
  // Груз стал «Под риском» — строка один раз мягко подсвечивается (класс risk-flash); повторно — только
  // после того, как риск сняли и он появился снова.
  const flash = atRisk && !riskFlashed.has(s.id);
  useEffect(() => {
    if (!atRisk) {
      riskFlashed.delete(s.id);
      return;
    }
    const t = window.setTimeout(() => riskFlashed.add(s.id), RISK_FLASH_MS);
    return () => window.clearTimeout(t);
  }, [atRisk, s.id]);
  const border = selected ? "var(--color-transit)" : atRisk ? "var(--color-risk-line)" : rerouted ? "var(--color-ok-line)" : "var(--color-line)";
  const tile = atRisk ? "var(--color-risk-soft)" : rerouted ? "var(--color-ok-soft)" : "var(--color-info-soft)";
  const iconColor = atRisk ? "var(--color-risk)" : rerouted ? "var(--color-rerouted)" : "var(--color-transit)";
  const prob = s.risk?.miss_probability ?? 0;

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`block h-[90px] w-full shrink-0 rounded-[12px] border pt-[10px] pr-[13px] pl-[11px] text-left transition-colors hover:brightness-110${flash ? " risk-flash" : ""}`}
      style={{ borderColor: border, background: selected ? "var(--color-info-soft)" : "var(--color-panel)" }}
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
          style={{ color: s.risk_level === "high" ? "var(--color-risk)" : s.risk_level === "medium" ? "var(--color-warn)" : "var(--color-muted)" }}
        >
          {formatPercent(prob)}
        </span>
      </div>
    </button>
  );
}

export function ShipmentList({ shipments, nodes, selectedId, onSelect }: Props) {
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
    <aside className="flex w-[320px] shrink-0 flex-col bg-panel shadow-[inset_-1px_0_0_var(--color-line)]">
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
            onlyRisk ? "border-[var(--color-risk-line)] bg-risk-soft text-risk-text" : "border-line-strong bg-panel text-muted hover:bg-tile"
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

      <div className="scroll-thin mt-[14px] flex min-h-0 flex-1 flex-col gap-[11px] overflow-y-auto px-5 pb-6">
        {visible.map((s) => (
          <ShipmentCard key={s.id} s={s} nodes={nodes} selected={s.id === selectedId} onSelect={() => onSelect(s.id)} />
        ))}
        {visible.length === 0 && <div className="pt-6 text-center text-[12.5px] text-muted">Ничего не найдено</div>}
      </div>

    </aside>
  );
}
