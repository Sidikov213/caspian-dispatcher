"use client";

import { CheckIcon, TriangleAlertIcon } from "./icons";

interface Props {
  tone: "ok" | "warn";
  title: string;
  text: string;
}

const TONE = {
  ok: { bg: "#132D29", border: "#2C6250", tile: "#1B4937", title: "#69E6A0" },
  warn: { bg: "#272219", border: "#594325", tile: "#3A2F1A", title: "#FCC965" },
} as const;

/** Подтверждение внизу карты справа («Маршрут изменён»). */
export function Toast({ tone, title, text }: Props) {
  const t = TONE[tone];
  return (
    <div
      role="status"
      data-map-ui
      className="absolute right-[22px] bottom-[73px] z-30 flex h-[57px] w-[380px] items-center rounded-[12px] border pl-[11px]"
      style={{ background: t.bg, borderColor: t.border }}
    >
      <span className="flex size-[34px] shrink-0 items-center justify-center rounded-[8px]" style={{ background: t.tile, color: t.title }}>
        {tone === "ok" ? <CheckIcon size={15} strokeWidth={2} /> : <TriangleAlertIcon size={15} />}
      </span>
      <div className="ml-[13px] min-w-0">
        <div className="truncate text-[14.5px] leading-[18px] font-bold" style={{ color: t.title }}>
          {title}
        </div>
        <div className="mt-[3px] truncate text-[12px] leading-[15px] text-muted">{text}</div>
      </div>
    </div>
  );
}
