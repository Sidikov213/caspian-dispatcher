"use client";

import type { GraphNode, NodeType } from "@/lib/types";
import { CloseIcon } from "./icons";

const TYPE: Record<NodeType, string> = { port: "Порт", station: "Станция", border: "Пункт пропуска", city: "Город" };

function host(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** Карточка узла по клику на карте: тип, загрузка, проверенные факты (Node.facts) и источники. */
export function NodeCard({ node, insetRight, onClose }: { node: GraphNode; insetRight: number; onClose(): void }) {
  return (
    <div
      data-map-ui
      className="absolute top-[96px] z-[500] w-[360px] rounded-[12px] border border-line bg-panel p-[16px] shadow-[0_16px_40px_var(--color-shadow)]"
      style={{ right: insetRight + 72 }}
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="Закрыть"
        className="absolute top-[12px] right-[12px] flex size-[32px] items-center justify-center rounded-[8px] border border-line text-muted hover:bg-tile"
      >
        <CloseIcon size={14} />
      </button>
      <div className="caps text-[10px] font-bold text-muted">
        {TYPE[node.type]} · {node.country}
      </div>
      <h3 className="mt-[6px] pr-[40px] text-[20px] leading-[26px] font-bold">{node.name}</h3>
      <div className="mt-[10px] text-[14px] text-muted">
        Загрузка {node.type === "port" ? "порта" : "узла"}:{" "}
        <span className="tnum font-bold text-text">{Math.round(node.congestion * 100)}%</span>
        {!node.facts?.length && <span> — оценка для демо</span>}
      </div>
      {node.facts?.length ? (
        <>
          <ul className="mt-[12px] flex flex-col gap-[6px] text-[14px] leading-[19px]">
            {node.facts.map((f) => (
              <li key={f} className="flex gap-[8px]">
                <span className="mt-[7px] size-[5px] shrink-0 rounded-full bg-rerouted" />
                {f}
              </li>
            ))}
          </ul>
          {node.sources?.length ? (
            <div className="mt-[12px] border-t border-line pt-[10px] text-[12px] text-muted">
              Источники:{" "}
              {node.sources.map((u, i) => (
                <span key={u}>
                  {i > 0 && ", "}
                  <a href={u} target="_blank" rel="noreferrer" className="text-transit-text hover:underline">
                    {host(u)}
                  </a>
                </span>
              ))}
            </div>
          ) : null}
        </>
      ) : (
        <p className="mt-[12px] text-[13px] text-muted">Проверенных фактов по этому узлу пока нет.</p>
      )}
    </div>
  );
}
