"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { WeatherSummary } from "@/lib/derive";
import { formatDecimal, formatInt, formatRub, formatSignedPct } from "@/lib/format";
import { clearSession, getStoredUser } from "@/lib/session";
import type { AuthUser, ScenarioPreset, Stats } from "@/lib/types";
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

function initialOf(user: AuthUser | null) {
  const src = user?.name?.trim() || user?.email || "Л";
  return src.charAt(0).toUpperCase();
}

export function AppHeader({ stats, co2Pct, weather, presets, onScenario, onReset }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const [user] = useState<AuthUser | null>(() => getStoredUser());
  const menuRef = useRef<HTMLDivElement>(null);
  const userRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open && !userOpen) return;
    const close = (e: MouseEvent) => {
      if (open && menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
      if (userOpen && userRef.current && !userRef.current.contains(e.target as Node)) setUserOpen(false);
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        setUserOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open, userOpen]);

  const hours = stats?.saved_hours ?? 0;

  return (
    <header className="relative z-30 flex h-20 shrink-0 items-center border-b border-line bg-panel pr-[21px] pl-5">
      <div className="flex w-[260px] items-center gap-[10px]">
        <LogoWordmark height={40} />
        <div className="min-w-0 border-l border-line pl-[10px]">
          <div className="text-[11.5px] leading-[14px] text-muted">Коридор «Север–Юг»</div>
        </div>
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

      <div className="ml-auto flex items-center gap-[16px]">
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
              className="absolute top-[47px] right-[-49px] w-[223px] rounded-[12px] border border-line bg-panel pt-px pb-[11px] shadow-[0_16px_40px_rgba(18,48,74,0.14)]"
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
              <button
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
              </button>
            </div>
          )}
        </div>

        <div ref={userRef} className="relative">
          <button
            type="button"
            onClick={() => setUserOpen((v) => !v)}
            aria-expanded={userOpen}
            title={user?.name ?? "Профиль"}
            className="flex size-[33px] items-center justify-center rounded-full border border-line bg-info-soft text-[12px] font-bold text-action transition-colors hover:bg-tile"
          >
            {initialOf(user)}
          </button>
          {userOpen && (
            <div className="absolute top-[42px] right-0 w-[220px] rounded-[12px] border border-line bg-panel p-[6px] shadow-[0_16px_40px_rgba(18,48,74,0.14)]">
              <div className="px-[10px] py-[8px]">
                <div className="truncate text-[13px] font-bold">{user?.name ?? "Пользователь"}</div>
                <div className="mt-[2px] truncate text-[11px] text-muted">{user?.email}</div>
                <div className="mt-[4px] text-[11px] font-semibold text-action">
                  {user?.role === "expeditor" ? "Экспедист" : "Логист"}
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  clearSession();
                  router.replace("/login");
                }}
                className="flex h-[36px] w-full items-center rounded-[8px] px-[10px] text-left text-[12.5px] font-semibold text-muted transition-colors hover:bg-tile hover:text-text"
              >
                Выйти
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
