"use client";

import { BoxIcon, FileIcon, LayersIcon, MapIcon, RouteIcon, SeaIcon, WavesIcon } from "./icons";

export type Section = "pult" | "shipments" | "sailings" | "decisions" | "journal" | "model" | "data";

export const SECTIONS: readonly Section[] = ["pult", "shipments", "sailings", "decisions", "journal", "model", "data"];

const ITEMS: { id: Section; label: string; icon: React.ReactNode }[] = [
  { id: "pult", label: "Пульт", icon: <MapIcon size={16} /> },
  { id: "shipments", label: "Грузы", icon: <BoxIcon size={16} /> },
  { id: "sailings", label: "Рейсы", icon: <SeaIcon size={16} /> },
  { id: "decisions", label: "Решения", icon: <RouteIcon size={16} /> },
  { id: "journal", label: "Документы и журнал", icon: <FileIcon size={16} /> },
  { id: "model", label: "Модель", icon: <LayersIcon size={16} /> },
  { id: "data", label: "Данные", icon: <WavesIcon size={16} /> },
];

export function SideNav({ active, badges, onSelect }: {
  active: Section;
  /** Счётчики у пунктов: открытые решения, грузы под риском. */
  badges: Partial<Record<Section, { value: number; tone: "risk" | "info" }>>;
  onSelect(section: Section): void;
}) {
  return (
    <nav aria-label="Разделы" className="flex w-[240px] shrink-0 flex-col gap-[4px] border-r border-line bg-panel px-[12px] pt-[16px]">
      {ITEMS.map((it) => {
        const on = it.id === active;
        const badge = badges[it.id];
        return (
          <button
            key={it.id}
            type="button"
            aria-current={on ? "page" : undefined}
            onClick={() => onSelect(it.id)}
            className={`flex h-[44px] items-center gap-[10px] rounded-[8px] px-[12px] text-left text-[14px] font-bold transition-colors ${
              on ? "bg-info-soft text-text" : "text-muted hover:bg-tile hover:text-text"
            }`}
          >
            <span className={on ? "text-action" : ""}>{it.icon}</span>
            <span className="min-w-0 flex-1 truncate">{it.label}</span>
            {badge && badge.value > 0 && (
              <span
                className={`tnum flex h-[20px] min-w-[20px] items-center justify-center rounded-full px-[6px] text-[11px] font-bold ${
                  badge.tone === "risk" ? "bg-risk-soft text-risk-text" : "bg-info-soft text-transit-text"
                }`}
              >
                {badge.value}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
