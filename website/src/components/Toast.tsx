import { CheckIcon, TriangleAlertIcon } from "./icons";

interface Props {
  title: string;
  text: string;
  tone?: "ok" | "warn";
}

const TONE = {
  ok: { bg: "#F0FDF4", border: "#BBF7D0", tile: "#DCFCE7", title: "#15803D" },
  warn: { bg: "#FFFBEB", border: "#FDE68A", tile: "#FEF3C7", title: "#B45309" },
} as const;

export function Toast({ title, text, tone = "ok" }: Props) {
  const t = TONE[tone];
  return (
    <div
      data-map-ui
      className="absolute right-[22px] bottom-[73px] z-30 flex h-[57px] w-[380px] items-center gap-[12px] rounded-[12px] border pr-[16px] pl-[12px] shadow-[0_12px_32px_rgba(18,48,74,0.12)]"
      style={{ background: t.bg, borderColor: t.border }}
    >
      <span className="flex size-[34px] shrink-0 items-center justify-center rounded-[8px]" style={{ background: t.tile, color: t.title }}>
        {tone === "ok" ? <CheckIcon size={16} strokeWidth={2} /> : <TriangleAlertIcon size={16} />}
      </span>
      <div className="min-w-0">
        <div className="text-[14px] leading-[17px] font-bold" style={{ color: t.title }}>
          {title}
        </div>
        <div className="mt-[2px] truncate text-[11.5px] leading-[14px] text-muted">{text}</div>
      </div>
    </div>
  );
}
