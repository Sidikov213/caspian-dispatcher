"use client";

import { formatDateTime, shipmentNumber, shortNodeName } from "@/lib/format";
import type { Block, GraphNode, LedgerVerify, Shipment } from "@/lib/types";
import { ShieldCheckIcon, TriangleAlertIcon } from "./icons";

interface Props {
  blocks: Block[];
  check: (LedgerVerify & { checked: number }) | null;
  verifying: boolean;
  shipments: Shipment[];
  nodes: Map<string, GraphNode>;
  onVerify(): void;
  onTamper(index: number): void;
  /** Кнопка «Подделать запись» — только демо и только с правом reset_demo. */
  canTamper?: boolean;
  children?: React.ReactNode;
}

const VISIBLE = 7;
const TAMPER_INDEX = 3;
/** Адаптивная сетка: хэш сжимается последним и обрезается, таблица не вылезает за панель. */
const COLS = "grid-cols-[56px_minmax(96px,0.9fr)_minmax(140px,1.3fr)_minmax(110px,1.1fr)_minmax(90px,0.9fr)_minmax(72px,0.7fr)]";

const EVENT_LABEL: Record<Block["event"], string> = {
  issued: "Пропуск выдан",
  reissued: "Пропуск переоформлен",
  verified: "Пропуск проверен",
};

/** «c271…9e16» */
function shortHash(h: string) {
  return h.length > 10 ? `${h.slice(0, 4)}…${h.slice(-4)}` : h;
}

const pad2 = (n: number) => String(n).padStart(2, "0");

function Banner({ check, lastTs }: { check: Props["check"]; lastTs: string | null }) {
  const broken = check ? !check.valid : false;
  const tone = broken
    ? { bg: "var(--color-risk-soft)", border: "var(--color-risk-line)", tile: "var(--color-risk-soft)", text: "var(--color-risk)" }
    : { bg: "var(--color-ok-soft)", border: "var(--color-ok-line)", tile: "var(--color-ok-soft)", text: "var(--color-rerouted)" };
  const title = !check ? "Проверяем цепочку…" : broken ? `Нарушение в записи №${(check.broken_at ?? 0) + 1}` : "Цепочка цела";
  const sub = !check
    ? "Сверяем хэши записей"
    : broken
      ? "Хэш записи не совпадает с предыдущим звеном"
      : `Проверено ${check.checked} ${plural(check.checked)}${lastTs ? ` · последнее обновление ${formatDateTime(lastTs)}` : ""}`;

  return (
    <div className="mt-[25px] flex h-[68px] items-start rounded-[12px] border pt-[13px] pl-[13px]" style={{ background: tone.bg, borderColor: tone.border }}>
      <span className="flex size-[40px] shrink-0 items-center justify-center rounded-[10px]" style={{ background: tone.tile, color: tone.text }}>
        {broken ? <TriangleAlertIcon size={17} /> : <ShieldCheckIcon size={17} />}
      </span>
      <div className="mt-[-2px] ml-[11px] min-w-0 pr-4">
        <div className="text-[17px] leading-[20px] font-bold" style={{ color: tone.text }}>
          {title}
        </div>
        <div className="mt-[5px] truncate text-[11px] leading-[14px] text-muted">{sub}</div>
      </div>
    </div>
  );
}

function plural(n: number) {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return "запись";
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "записи";
  return "записей";
}

export function LedgerView({ blocks, check, verifying, shipments, nodes, onVerify, onTamper, canTamper = true, children }: Props) {
  const rows = [...blocks].sort((a, b) => b.index - a.index).slice(0, VISIBLE);
  const byId = new Map(shipments.map((s) => [s.id, s]));
  const lastTs = blocks.length ? blocks[blocks.length - 1].ts : null;
  // Подделываем запись №4 (индекс 3), как в макете; если её нет на экране, берём запись из середины видимой части.
  const target = rows.find((r) => r.index === TAMPER_INDEX)?.index ?? (rows.length ? rows[Math.floor(rows.length / 2)].index : null);

  return (
    <div className="scroll-thin relative min-w-0 flex-1 overflow-y-auto bg-bg px-5 pb-8 md:px-8">
      <div className="flex flex-wrap items-start justify-between gap-4 pt-[28px]">
        <div className="min-w-0">
          <div className="caps text-[10px] leading-[12px] font-bold text-muted">Документы и журнал &nbsp;/&nbsp; Реестр</div>
          <h1 className="mt-[14px] text-[28px] leading-[34px] font-bold md:text-[34px] md:leading-[40px]">Реестр пропусков</h1>
          <p className="mt-[6px] text-[12.5px] leading-[16px] text-muted">Выдача, переоформление и проверка целостности</p>
        </div>
        <button
          type="button"
          onClick={onVerify}
          disabled={verifying}
          className="flex h-[46px] w-full max-w-[258px] shrink-0 items-center justify-center gap-[10px] rounded-[8px] bg-action text-[13px] font-bold text-white transition-colors hover:bg-action-hover disabled:opacity-70 sm:w-[258px]"
        >
          <ShieldCheckIcon size={15} />
          {verifying ? "Проверяем…" : "Проверить целостность"}
        </button>
      </div>

      <Banner check={check} lastTs={lastTs} />

      <div className="mt-[18px] overflow-hidden rounded-[12px] border border-line bg-panel">
        <div className="scroll-thin overflow-x-auto">
          <div className="min-w-[640px]">
            <div className={`caps grid h-[41px] items-center border-b border-line text-[9px] font-bold text-muted ${COLS}`}>
              <span className="pl-[16px]">№</span>
              <span>Время</span>
              <span>Событие</span>
              <span>Груз</span>
              <span>Пункт пропуска</span>
              <span className="pr-4">Хэш</span>
            </div>
            {rows.length === 0 && <div className="py-10 text-center text-[12.5px] text-muted">Записей пока нет</div>}
            {rows.map((b, i) => {
              const reissued = b.event === "reissued";
              const ship = byId.get(b.shipment_id);
              const node = nodes.get(b.checkpoint_node);
              const broken = check && !check.valid && check.broken_at === b.index;
              const last = i === rows.length - 1;
              return (
                <div
                  key={b.index}
                  className={`relative grid h-[60px] items-center text-[12px] ${COLS}`}
                  style={broken ? { background: "var(--color-risk-soft)" } : undefined}
                >
                  <span className="relative z-10 pl-[16px]">
                    <span
                      className="tnum flex size-[26px] items-center justify-center rounded-[7px] border text-[10.5px] font-bold"
                      style={{
                        background: broken ? "var(--color-risk-soft)" : "var(--color-tile)",
                        borderColor: broken ? "var(--color-risk-line)" : "var(--color-line)",
                        color: broken ? "var(--color-risk)" : reissued ? "var(--color-rerouted)" : "var(--color-transit)",
                      }}
                    >
                      {pad2(b.index + 1)}
                    </span>
                  </span>
                  {!last && <span className="absolute top-[43px] left-[28.5px] h-[34px] w-px bg-line-strong" />}
                  {!last && <span className="absolute right-0 bottom-0 left-[49px] h-px bg-line" />}
                  <span className="tnum truncate pr-2 text-muted">{formatDateTime(b.ts)}</span>
                  <span className={`truncate pr-2 text-[13px] font-bold ${reissued ? "text-ok" : ""}`}>{EVENT_LABEL[b.event]}</span>
                  <span className="truncate pr-2">{ship ? `${shipmentNumber(ship.id)} ${ship.title}` : shipmentNumber(b.shipment_id)}</span>
                  <span className="truncate pr-2">{node ? shortNodeName(node.name) : b.checkpoint_node}</span>
                  <span className="tnum truncate pr-4 text-[11.5px] text-transit-text" title={b.hash}>
                    {shortHash(b.hash)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="mt-[14px] flex flex-wrap items-center justify-between gap-3">
        <span className="text-[11px] leading-[14px] text-muted">
          Показаны последние {rows.length} из {blocks.length} {plural(blocks.length)}
        </span>
        {canTamper && <button
          type="button"
          disabled={target === null}
          onClick={() => target !== null && onTamper(target)}
          className="flex h-[37px] w-[209px] items-center justify-center gap-[10px] rounded-[8px] border border-line-strong bg-panel text-[12.5px] font-bold transition-colors hover:bg-tile disabled:opacity-50"
        >
          <TriangleAlertIcon size={14} className="text-transit-text" />
          Подделать запись
        </button>}
      </div>
      {children}
    </div>
  );
}
