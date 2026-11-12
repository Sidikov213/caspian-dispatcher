"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "@/lib/api";
import { checkpointLabel } from "@/lib/derive";
import { formatDateTime, shipmentNumber } from "@/lib/format";
import type { Block, GraphNode, Pass, PassVerify, Shipment } from "@/lib/types";
import { CheckIcon, CloseIcon, ShieldCheckIcon } from "./icons";
import { QrCode } from "./QrCode";

const STATUS: Record<Pass["status"], string> = { active: "Действует", reissued: "Переоформлен", revoked: "Отозван" };

/** Окно пропуска: крупный QR, реквизиты, запись в реестре и проверка POST /passes/verify. */
export function PassModal({ pass, shipment, nodes, onClose }: {
  pass: Pass;
  shipment: Shipment;
  nodes: Map<string, GraphNode>;
  onClose(): void;
}) {
  const [block, setBlock] = useState<Block | null>(null);
  const [check, setCheck] = useState<PassVerify | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [onClose]);

  // номер записи в журнале — блок, на который ссылается пропуск (block_hash)
  useEffect(() => {
    let alive = true;
    api.getLedger().then((ledger) => alive && setBlock(ledger.find((b) => b.hash === pass.block_hash) ?? null)).catch(() => {});
    return () => {
      alive = false;
    };
  }, [pass.block_hash]);

  const verify = async () => {
    setBusy(true);
    setError(null);
    try {
      setCheck(await api.verifyPass(pass.token));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const where = checkpointLabel(nodes.get(pass.checkpoint_node), pass.checkpoint_node);
  const shortHash = `${pass.block_hash.slice(0, 8)}…${pass.block_hash.slice(-6)}`;

  // портал в body: окно поверх карты и панелей, а не внутри слоя панели двойника
  return createPortal(
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-[rgba(11,18,32,0.55)] p-4"
      onMouseDown={(e) => {
        if (box.current && !box.current.contains(e.target as Node)) onClose();
      }}
    >
      <div
        ref={box}
        role="dialog"
        aria-modal="true"
        aria-label="Пропуск"
        className="relative w-full max-w-[460px] rounded-[12px] border border-line bg-panel p-6 shadow-2xl"
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Закрыть"
          className="absolute top-4 right-4 flex size-[36px] items-center justify-center rounded-[8px] border border-line text-muted hover:bg-tile"
        >
          <CloseIcon size={16} />
        </button>
        <div className="caps text-[11px] font-bold text-cyan">Демонстрационный пропуск</div>
        <h2 className="mt-1 text-[22px] leading-[28px] font-bold">
          {shipmentNumber(shipment.id)} {shipment.title}
        </h2>

        <div className="mt-4 flex justify-center rounded-[12px] bg-panel p-4">
          <QrCode value={pass.token} size={240} />
        </div>

        <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-[15px]">
          <dt className="text-muted">Пункт пропуска</dt>
          <dd className="font-bold">{where}</dd>
          <dt className="text-muted">Действует до</dt>
          <dd className="font-bold">{formatDateTime(pass.valid_until)}</dd>
          <dt className="text-muted">Статус</dt>
          <dd className="font-bold">{STATUS[pass.status] ?? pass.status}</dd>
          <dt className="text-muted">Запись в журнале</dt>
          <dd className="font-bold">
            {block ? `№${String(block.index).padStart(2, "0")}` : "—"}
            <span className="ml-2 font-mono text-[13px] font-normal text-muted">{shortHash}</span>
          </dd>
        </dl>

        <button
          type="button"
          onClick={verify}
          disabled={busy}
          className="mt-5 flex h-[52px] w-full items-center justify-center gap-2 rounded-[8px] bg-action text-[16px] font-bold text-white hover:bg-action-hover disabled:opacity-60"
        >
          <ShieldCheckIcon size={18} />
          {busy ? "Проверяем…" : "Проверить"}
        </button>
        {check && (
          <div
            className={`mt-3 flex items-start gap-2 rounded-[8px] p-3 text-[15px] font-bold ${check.valid ? "bg-rerouted-soft text-rerouted-text" : "bg-risk-soft text-risk-text"}`}
          >
            {check.valid ? <CheckIcon size={18} /> : <CloseIcon size={18} />}
            <span>{check.valid ? "Действителен" : `Недействителен: ${check.reason ?? "причина не указана"}`}</span>
          </div>
        )}
        {error && <div className="mt-3 text-[14px] text-risk-text">{error}</div>}
      </div>
    </div>,
    document.body,
  );
}
