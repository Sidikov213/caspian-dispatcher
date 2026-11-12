"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { WeatherSummary } from "@/lib/derive";
import { formatDecimal, formatInt, formatRub, formatSignedPct } from "@/lib/format";
import { ROLE_LABEL, can, clearSession, useSessionUser } from "@/lib/session";
import { setSiteTheme, useSiteTheme } from "@/lib/theme";
import type { ScenarioPreset, Stats } from "@/lib/types";
import { ChevronDownIcon, ClockIcon, CloseIcon, LeafIcon, LogoWordmark, RouteIcon, StormIcon, WavesIcon } from "./icons";

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

function ThemeToggle() {
  const theme = useSiteTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      onClick={() => setSiteTheme(next)}
      title={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
      aria-label={theme === "dark" ? "Включить светлую тему" : "Включить тёмную тему"}
      className="flex size-[40px] items-center justify-center rounded-[8px] border border-line-strong bg-panel text-muted transition-colors hover:bg-tile hover:text-text"
    >
      {theme === "dark" ? (
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
          <circle cx="12" cy="12" r="4.2" />
          <path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6" />
        </svg>
      ) : (
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round">
          <path d="M20.5 14.2A8.5 8.5 0 1 1 9.8 3.5a6.8 6.8 0 0 0 10.7 10.7Z" />
        </svg>
      )}
    </button>
  );
}

export function AppHeader({ stats, co2Pct, weather, presets, onScenario, onReset }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const user = useSessionUser();
  const canScenario = can(user, "run_scenario");
  const canReset = can(user, "reset_demo");
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const hours = stats?.saved_hours ?? 0;

  return (
    <header className="relative z-30 flex h-20 shrink-0 items-center border-b border-line bg-panel pr-[21px] pl-5">
      <div className="flex w-[200px] items-center gap-[10px]" title="Коридор «Север–Юг»">
        <LogoWordmark height={40} />

      </div>

      <div className="h-[38px] w-px bg-line" />

      <div className="caps ml-[21px] w-[151px] self-start pt-[25px] text-[10.5px] leading-[12px] font-bold text-muted">
        Расчётная экономия
      </div>
      <div className="w-[125px]">
        <Saved icon={<ClockIcon size={15} />} value={formatInt(hours)} label="груз-часов" good={hours > 0} />
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

      <div className="ml-auto flex items-center gap-[12px]">
        <ThemeToggle />
        {(canScenario || canReset) && (
        <div ref={menuRef} className="relative">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="flex h-[40px] w-[127px] items-center justify-center gap-[10px] rounded-[8px] border border-line-strong bg-panel text-[14px] font-bold transition-colors hover:bg-tile"
          >
            <ChevronDownIcon size={14} strokeWidth={2.2} className="text-action" />
            Сценарий
          </button>
          {open && (
            <div
              role="menu"
              className="absolute top-[47px] right-[-49px] w-[223px] rounded-[12px] border border-line bg-panel pt-px pb-[11px] shadow-[0_16px_40px_var(--color-shadow)]"
            >
              {canScenario && presets.map((p, i) => (
                <button
                  key={p.key}
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setOpen(false);
                    onScenario(p.key);
                  }}
                  className={`flex h-[36px] w-full items-center gap-[9px] px-[12px] text-left text-[11px] transition-colors hover:bg-tile ${
                    i === 0 ? "font-bold text-text" : "font-medium text-muted"
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
              {canReset && <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  onReset();
                }}
                className="flex h-[36px] w-full items-center gap-[9px] px-[12px] text-left text-[11px] font-medium text-muted transition-colors hover:bg-tile"
              >
                <CloseIcon size={14} className="text-muted" />
                Сбросить
              </button>}
            </div>
          )}
        </div>
        )}

        <div className="flex items-center gap-[12px] border-l border-line pl-[16px]">
          <div className="text-right">
            <div className="max-w-[180px] truncate text-[13px] leading-[16px] font-bold">{user?.name ?? "Пользователь"}</div>
            <div className="mt-[3px] text-[11.5px] leading-[14px] text-muted">{user ? ROLE_LABEL[user.role] : ""}</div>
          </div>
          <button
            type="button"
            onClick={() => {
              clearSession();
              router.replace("/login");
            }}
            className="h-[40px] rounded-[8px] border border-line-strong bg-panel px-[14px] text-[13px] font-bold text-muted transition-colors hover:bg-tile hover:text-text"
          >
            Выйти
          </button>
        </div>
      </div>
    </header>
  );
}
