"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { WeatherSummary } from "@/lib/derive";
import { formatDecimal, formatInt, formatRub, formatSignedPct } from "@/lib/format";
import { ROLE_LABEL, can, clearSession, useSessionUser } from "@/lib/session";
import { setSiteTheme, useSiteTheme } from "@/lib/theme";
import { useCountUp } from "@/lib/useCountUp";
import { DemoBadge } from "./DemoBadge";
import type { PlaybackSpeed, ScenarioPreset, Stats } from "@/lib/types";
import { ChevronDownIcon, ClockIcon, CloseIcon, HazardIcon, LeafIcon, LogoWordmark, RouteIcon, StormIcon, WavesIcon } from "./icons";

interface Props {
  stats: Stats | null;
  co2Pct: number;
  weather: WeatherSummary | null;
  presets: ScenarioPreset[];
  onScenario(preset: string): void;
  onReset(): void;
  /** Ускоренный просмотр движения; null — не поддерживается (моки). */
  playback?: PlaybackSpeed | null;
  onPlayback?(speed: PlaybackSpeed): void;
}

const SPEEDS: { v: PlaybackSpeed; label: string }[] = [
  { v: 0, label: "Пауза" },
  { v: 60, label: "×60" },
  { v: 600, label: "×600" },
];

/** «Движение: пауза / ×60 / ×600» — двигает только значки грузов на карте. */
function PlaybackSwitch({ value, onChange }: { value: PlaybackSpeed; onChange(v: PlaybackSpeed): void }) {
  return (
    <div className="flex items-center gap-[8px]" role="group" aria-label="Движение грузов на карте">
      <span className="text-[12px] font-bold text-muted">Движение</span>
      <div className="flex h-[40px] items-center rounded-[8px] border border-line-strong bg-panel p-[3px]">
        {SPEEDS.map((s) => (
          <button
            key={s.v}
            type="button"
            aria-pressed={value === s.v}
            onClick={() => onChange(s.v)}
            className={`tnum h-[32px] rounded-[6px] px-[10px] text-[13px] font-bold transition-colors ${
              value === s.v ? "bg-action text-white" : "text-muted hover:bg-tile hover:text-text"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Saved({ icon, value, label, good, flash = 0 }: { icon: React.ReactNode; value: string; label: string; good?: boolean; flash?: number }) {
  // flash растёт на 1, когда счётчик добежал до нового значения: подсветка включается один раз и после
  // окончания класс снимается — разметка возвращается ровно к прежней.
  const [played, setPlayed] = useState(0);
  return (
    <div
      className={`flex items-start gap-[9px]${flash > played ? " saved-flash" : ""}`}
      onAnimationEnd={() => setPlayed(flash)}
    >
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

export function AppHeader({ stats, co2Pct, weather, presets, onScenario, onReset, playback, onPlayback }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const user = useSessionUser();
  const canScenario = can(user, "run_scenario");
  const canReset = can(user, "reset_demo");
  // Главный сценарий — по флагу main с сервера (ice_north); шторм — стресс-тест, второй ряд с подписью.
  const main = presets.find((p) => p.main) ?? presets[0] ?? null;
  const stress = presets.filter((p) => p !== main && p.hazard === "storm");
  const others = presets.filter((p) => p !== main && p.hazard !== "storm");
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
  // Счётчики добегают до нового значения за 1 с (только показ; числа — с сервера, в конце ровно они).
  const hoursUp = useCountUp(hours);
  const rubUp = useCountUp(stats?.saved_rub ?? 0);
  const co2Up = useCountUp(co2Pct);

  return (
    <header className="relative z-30 flex h-20 shrink-0 items-center border-b border-line bg-panel pr-[21px] pl-5">
      {/* Плашка висит на верхней кромке шапки: место в ряду не занимает, счётчики не сдвигает. */}
      <div className="absolute top-0 left-1/2 z-10 -translate-x-1/2">
        <DemoBadge hanging />
      </div>
      <div className="flex w-[200px] items-center gap-[10px]" title="Коридор «Север–Юг»">
        <LogoWordmark height={40} />

      </div>

      <div className="h-[38px] w-px bg-line" />

      <div className="caps ml-[21px] w-[151px] self-start pt-[25px] text-[10.5px] leading-[12px] font-bold text-muted">
        Расчётная экономия
      </div>
      <div className="w-[125px]">
        <Saved icon={<ClockIcon size={15} />} value={formatInt(hoursUp.value)} label="груз-часов" good={hours > 0} flash={hoursUp.flash} />
      </div>
      <div className="w-[159px]">
        <Saved icon={<RouteIcon size={15} />} value={formatRub(rubUp.value)} label="Расходы" good={(stats?.saved_rub ?? 0) > 0} flash={rubUp.flash} />
      </div>
      <div className="w-[141px]">
        <Saved icon={<LeafIcon size={15} />} value={formatSignedPct(co2Up.value)} label="CO₂" good={co2Pct < -0.05} flash={co2Up.flash} />
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
        {canScenario && playback != null && onPlayback && <PlaybackSwitch value={playback} onChange={onPlayback} />}
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
              className="absolute top-[47px] right-[-49px] w-[280px] rounded-[12px] border border-line bg-panel pt-px pb-[11px] shadow-[0_16px_40px_var(--color-shadow)]"
            >
              {canScenario && main && (
                <div className="px-[10px] pt-[10px] pb-[6px]">
                  <div className="caps px-[2px] pb-[6px] text-[9.5px] font-bold text-muted">Главный сценарий</div>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setOpen(false);
                      onScenario(main.key);
                    }}
                    className="flex h-[44px] w-full items-center gap-[10px] rounded-[8px] bg-action px-[12px] text-left text-[13px] font-bold text-white transition-colors hover:bg-action-hover"
                  >
                    <HazardIcon hazard={main.hazard} size={16} />
                    {main.title}
                  </button>
                </div>
              )}
              {canScenario && stress.length > 0 && (
                <div className="border-t border-line px-[12px] pt-[8px] pb-[2px]">
                  <div className="caps text-[9.5px] font-bold text-muted">Стресс-тесты</div>
                  {stress[0].note && <div className="mt-[3px] text-[10.5px] leading-[13px] text-warn-text">{stress[0].note}</div>}
                </div>
              )}
              {canScenario && [...stress, ...others].map((p, i) => (
                <div key={p.key} className={i === stress.length && i > 0 ? "mt-[4px] border-t border-line pt-[4px]" : undefined}>
                <button
                  type="button"
                  role="menuitem"
                  title={p.note ?? undefined}
                  onClick={() => {
                    setOpen(false);
                    onScenario(p.key);
                  }}
                  className="flex h-[34px] w-full items-center gap-[9px] px-[12px] text-left text-[11.5px] font-medium text-muted transition-colors hover:bg-tile hover:text-text"
                >
                  <HazardIcon hazard={p.hazard} size={14} className={p.hazard === "storm" ? "text-risk-text" : "text-muted"} />
                  {p.title}
                </button>
                </div>
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
