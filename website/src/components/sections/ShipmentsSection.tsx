"use client";

import { FormEvent, useMemo, useState } from "react";
import { ApiError } from "@/lib/api";
import { RISK_LEVEL_LABEL } from "@/lib/derive";
import { formatDateTime, formatDecimal, formatHoursDelta, formatPercent, shipmentNumber } from "@/lib/format";
import type { GraphNode, Pass, RiskLevel, Shipment, ShipmentCreate } from "@/lib/types";
import { CloseIcon, PlusIcon } from "../icons";
import { StatusChip } from "../StatusChip";
import { Empty, Pill, Row, SectionPage, Table, nodeName } from "./common";

const COLS = "60px minmax(120px,1fr) 64px minmax(150px,1.3fr) 128px 76px 128px 80px 150px";
const RISK_TONE: Record<RiskLevel, "ok" | "warn" | "risk"> = { low: "ok", medium: "warn", high: "risk" };
const PASS_LABEL: Record<Pass["status"], string> = { active: "Действует", reissued: "Переоформлен", revoked: "Отозван" };

/** Типы груза, которые принимает POST /api/shipments (CLAUDE.md, раздел 5). */
const CARGO_TYPES: { id: string; label: string }[] = [
  { id: "grain", label: "Зерно" },
  { id: "metal", label: "Металл" },
  { id: "equipment", label: "Оборудование" },
  { id: "textile", label: "Текстиль" },
  { id: "fertilizer", label: "Удобрения" },
];

/** Отклонение прибытия к плану: разница двух меток сервера (eta и planned_eta), без своих расчётов. */
function deviationH(s: Shipment) {
  return Math.round((Date.parse(s.eta) - Date.parse(s.planned_eta)) / 3_600_000);
}

export function ShipmentsSection({
  shipments,
  nodes,
  passes,
  canCreate,
  onOpen,
  onCreate,
}: {
  shipments: Shipment[];
  nodes: Map<string, GraphNode>;
  passes: Map<string, Pass>;
  canCreate: boolean;
  onOpen(id: string): void;
  onCreate(body: ShipmentCreate): Promise<Shipment>;
}) {
  const [creating, setCreating] = useState(false);
  return (
    <SectionPage
      kicker="Грузы / Цифровые двойники"
      title="Грузы"
      subtitle="Клик по строке открывает двойник груза на пульте"
      actions={
        canCreate && (
          <button
            type="button"
            onClick={() => setCreating(true)}
            className="flex h-[52px] items-center gap-[10px] rounded-[8px] bg-action px-[20px] text-[15px] font-bold text-white transition-colors hover:bg-action-hover"
          >
            <PlusIcon size={16} />
            Новый груз
          </button>
        )
      }
    >
      <Table cols={COLS} head={["№", "Груз", "Вес", "Маршрут", "Статус", "Риск", "Прибытие", "К плану", "Пропуск"]} minWidth={1060}>
        {shipments.length === 0 && <Empty>Грузов нет</Empty>}
        {shipments.map((s) => {
          const dev = deviationH(s);
          const pass = s.pass_id ? passes.get(s.pass_id) : null;
          return (
            <Row key={s.id} cols={COLS} onClick={() => onOpen(s.id)}>
              <span className="tnum font-bold">{shipmentNumber(s.id)}</span>
              <span className="truncate font-bold">{s.title}</span>
              <span className="tnum text-muted">{formatDecimal(s.weight_t, s.weight_t % 1 ? 1 : 0)}&nbsp;т</span>
              <span className="truncate text-muted">
                {nodeName(nodes, s.origin)} → {nodeName(nodes, s.destination)}
              </span>
              <span>
                <StatusChip status={s.display_status} />
              </span>
              <span>
                {s.risk ? (
                  <Pill tone={RISK_TONE[s.risk.level]}>
                    <span className="tnum">{formatPercent(s.risk.miss_probability)}</span>
                    <span className="sr-only"> {RISK_LEVEL_LABEL[s.risk.level]}</span>
                  </Pill>
                ) : (
                  "—"
                )}
              </span>
              <span className="tnum text-[14px]">{formatDateTime(s.eta)}</span>
              <span className={`tnum font-bold ${dev > 0 ? "text-risk-text" : dev < 0 ? "text-rerouted-text" : "text-muted"}`}>
                {formatHoursDelta(dev)}
              </span>
              <span className="text-[13px]">
                {s.pass_state === "reissue_pending" ? (
                  <Pill tone="warn">Ждёт переоформления</Pill>
                ) : pass ? (
                  <Pill tone={pass.status === "active" ? "ok" : "muted"}>{PASS_LABEL[pass.status]}</Pill>
                ) : (
                  <span className="text-muted">Нет</span>
                )}
              </span>
            </Row>
          );
        })}
      </Table>
      {creating && <NewShipmentDialog nodes={nodes} onClose={() => setCreating(false)} onCreate={onCreate} onOpen={onOpen} />}
    </SectionPage>
  );
}

const FIELD_LABEL: Record<string, string> = {
  title: "Название",
  cargo_type: "Тип груза",
  weight_t: "Вес",
  origin: "Откуда",
  destination: "Куда",
};

function NewShipmentDialog({
  nodes,
  onClose,
  onCreate,
  onOpen,
}: {
  nodes: Map<string, GraphNode>;
  onClose(): void;
  onCreate(body: ShipmentCreate): Promise<Shipment>;
  onOpen(id: string): void;
}) {
  // Пункты — только узлы графа; порты и города первыми, переходы границы в конце.
  const points = useMemo(
    () =>
      [...nodes.values()].sort((a, b) => Number(a.type === "border") - Number(b.type === "border") || a.name.localeCompare(b.name, "ru")),
    [nodes],
  );
  const [title, setTitle] = useState("");
  const [cargo, setCargo] = useState(CARGO_TYPES[0].id);
  const [weight, setWeight] = useState("100");
  const [origin, setOrigin] = useState(nodes.has("astrakhan") ? "astrakhan" : (points[0]?.id ?? ""));
  const [destination, setDestination] = useState(nodes.has("anzali") ? "anzali" : (points[1]?.id ?? ""));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const sh = await onCreate({ title: title.trim(), cargo_type: cargo, weight_t: Number(weight.replace(",", ".")), origin, destination });
      onClose();
      onOpen(sh.id);
    } catch (err) {
      if (err instanceof ApiError) {
        const field = err.message.split(":")[0].replace(/^body\./, "");
        setError(FIELD_LABEL[field] ? `${FIELD_LABEL[field]}: ${err.message.split(":").slice(1).join(":").trim()}` : err.message);
      } else setError("Не удалось создать груз");
    } finally {
      setBusy(false);
    }
  }

  const field =
    "h-[48px] w-full rounded-[8px] border border-line bg-field px-[14px] text-[15px] text-text outline-none focus:border-action";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onMouseDown={onClose}>
      <form
        onSubmit={submit}
        onMouseDown={(e) => e.stopPropagation()}
        className="relative w-[520px] rounded-[12px] border border-line bg-panel p-[24px] shadow-[0_24px_60px_var(--color-shadow)]"
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Закрыть"
          className="absolute top-[16px] right-[16px] flex size-[40px] items-center justify-center rounded-[8px] border border-line text-muted hover:bg-tile"
        >
          <CloseIcon size={16} />
        </button>
        <h2 className="text-[24px] leading-[32px] font-bold">Новый груз</h2>
        <p className="mt-[4px] text-[15px] text-muted">Маршрут подберёт сервер по графу и расписанию</p>

        <div className="mt-[24px] grid grid-cols-2 gap-[16px]">
          <label className="col-span-2 block">
            <span className="mb-[8px] block text-[13px] font-bold text-muted">Название</span>
            <input required maxLength={120} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Пшеница" className={field} />
          </label>
          <label className="block">
            <span className="mb-[8px] block text-[13px] font-bold text-muted">Тип груза</span>
            <select value={cargo} onChange={(e) => setCargo(e.target.value)} className={field}>
              {CARGO_TYPES.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-[8px] block text-[13px] font-bold text-muted">Вес, т (до 5000)</span>
            <input required inputMode="decimal" value={weight} onChange={(e) => setWeight(e.target.value)} className={`${field} tnum`} />
          </label>
          <label className="block">
            <span className="mb-[8px] block text-[13px] font-bold text-muted">Откуда</span>
            <select value={origin} onChange={(e) => setOrigin(e.target.value)} className={field}>
              {points.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-[8px] block text-[13px] font-bold text-muted">Куда</span>
            <select value={destination} onChange={(e) => setDestination(e.target.value)} className={field}>
              {points.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.name}
                </option>
              ))}
            </select>
          </label>
        </div>

        {error && (
          <div className="mt-[16px] rounded-[8px] border border-risk-line bg-risk-soft px-[12px] py-[10px] text-[14px] font-semibold text-risk-text">
            {error}
          </div>
        )}

        <div className="mt-[24px] flex justify-end gap-[12px]">
          <button type="button" onClick={onClose} className="h-[52px] rounded-[8px] border border-line-strong px-[20px] text-[15px] font-bold hover:bg-tile">
            Отмена
          </button>
          <button
            type="submit"
            disabled={busy}
            className="h-[52px] rounded-[8px] bg-action px-[24px] text-[15px] font-bold text-white hover:bg-action-hover disabled:opacity-60"
          >
            {busy ? "Создаём…" : "Создать груз"}
          </button>
        </div>
      </form>
    </div>
  );
}
