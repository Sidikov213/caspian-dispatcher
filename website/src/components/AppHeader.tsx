"use client";

import { useEffect, useRef, useState } from "react";
import type { WeatherSummary } from "@/lib/derive";
import { formatDecimal, formatInt, formatRub, formatSignedPct } from "@/lib/format";
import type { ScenarioPreset, Stats } from "@/lib/types";
import { ChevronDownIcon, ClockIcon, CloseIcon, LeafIcon, LogoMark, RouteIcon, StormIcon, WavesIcon } from "./icons";

interface Props {
  stats: Stats | null;
  co2Pct: number;
  weather: WeatherSummary | null;
  presets: ScenarioPreset[];
  onScenario(preset: string): void;
  onReset(): void;
}

function Saved({ icon, value, label, good }: { icon: React.ReactNode; value: string; label: string; good?: boolean }) {
  return (
    <div className="flex items-start gap-[9px]">
      <span className={`mt-[2px] ${good ? "text-ok" : "text-muted"}`}>{icon}</span>
      <div>
        <div className={`tnum text-[18px] leading-[22px] font-bold ${good ? "text-ok" : ""}`}>{value}</div>
        <div className="mt-[3px] text-[11.5px] leading-[14px] text-muted">{label}</div>
      </div>
    </div>
  );
}

export function AppHeader({ stats, co2Pct, weather, presets, onScenario, onReset }: Props) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const hours = stats?.saved_hours ?? 0;

  return (
    <header className="relative z-30 flex h-20 shrink-0 items-center border-b border-line bg-bg pr-[21px] pl-5">
      <LogoMark size={50} />
      <div className="ml-[7px] w-[253px]">
        <div className="text-[16px] leading-[20px] font-bold tracking-[0.005em]">Каспийский диспетчер</div>
        <div className="mt-[3px] text-[11.5px] leading-[14px] text-muted">Коридор «Север–Юг»</div>
      </div>

      <div className="h-[38px] w-px bg-line" />

      <div className="caps ml-[21px] w-[151px] self-start pt-[25px] text-[10.5px] leading-[12px] font-bold text-muted">
        Сэкономлено
      </div>
      <div className="w-[125px]">
        <Saved icon={<ClockIcon size={15} />} value={`${formatInt(hours)}\u00A0ч`} label="Время" good={hours > 0} />
      </div>
      <div className="w-[159px]">
        <Saved icon={<RouteIcon size={15} />} value={formatRub(stats?.saved_rub ?? 0)} label="Расходы" good={(stats?.saved_rub ?? 0) > 0} />
      </div>
      <div className="w-[141px]">
        <Saved icon={<LeafIcon size={15} />} value={formatSignedPct(co2Pct)} label="CO₂" good={co2Pct < -0.05} />
      </div>

      <div className="h-[38px] w-px bg-line" />

      <div className="ml-[23px] flex items-center gap-[11px]">
        {weather?.storm ? (
          <StormIcon size={20} className="text-risk-text" />
        ) : (
          <WavesIcon size={20} className="text-cyan" />
        )}
        <div>
          <div className={`text-[14px] leading-[17px] font-bold ${weather?.storm ? "text-risk-text" : ""}`}>
            {weather ? `Волна ${formatDecimal(weather.waveM)}\u00A0м` : "Волна —"}
          </div>
          <div className="mt-[5px] text-[11.5px] leading-[14px] text-muted">
            {weather ? `Ветер ${formatInt(weather.windMs)}\u00A0м/с` : "Нет данных"}
          </div>
        </div>
      </div>

      <div className="ml-auto flex items-center gap-[16px]">
        <div ref={menuRef} className="relative">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="flex h-[40px] w-[127px] items-center justify-center gap-[10px] rounded-[9px] border border-line-strong bg-tile text-[14px] font-bold transition-colors hover:bg-[#1b2a42]"
          >
            <ChevronDownIcon size={14} strokeWidth={2.2} className="text-transit-text" />
            Сценарий
          </button>
          {open && (
            <div
              role="menu"
              className="absolute top-[47px] right-[-49px] w-[223px] rounded-[10px] border border-line-strong bg-panel pt-px pb-[11px] shadow-[0_16px_40px_rgba(0,0,0,0.45)]"
            >
              {presets.map((p, i) => (
                <button
                  key={p.key}
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setOpen(false);
                    onScenario(p.key);
                  }}
                  className={`flex h-[36px] w-full items-center gap-[9px] px-[12px] text-left text-[11px] transition-colors hover:bg-tile ${
                    i === 0 ? "font-bold text-text" : "font-medium text-[#C3CCDA]"
                  }`}
                >
                  {p.key === "storm_north" ? (
                    <StormIcon size={14} className="text-risk-text" />
                  ) : (
                    <WavesIcon size={14} className="text-muted" />
                  )}
                  {p.title}
                </button>
              ))}
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  onReset();
                }}
                className="flex h-[36px] w-full items-center gap-[9px] px-[12px] text-left text-[11px] font-medium text-[#C3CCDA] transition-colors hover:bg-tile"
              >
                <CloseIcon size={14} className="text-muted" />
                Сбросить
              </button>
            </div>
          )}
        </div>
        <div className="flex size-[33px] items-center justify-center rounded-full border border-[#223047] bg-tile text-[12px] font-bold text-transit-text">
          Л
        </div>
      </div>
    </header>
  );
}
