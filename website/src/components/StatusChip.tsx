import { STATUS_LABEL } from "@/lib/derive";
import type { DisplayStatus } from "@/lib/types";

/** Светлые подложки статусов: бриф (красная / жёлтая / зелёная / синяя). */
const TONE: Record<DisplayStatus, { bg: string; dot: string; text: string }> = {
  planned: { bg: "var(--color-tile)", dot: "var(--color-muted)", text: "var(--color-muted)" },
  in_transit: { bg: "var(--color-info-soft)", dot: "var(--color-transit)", text: "var(--color-transit)" },
  at_risk: { bg: "var(--color-risk-soft)", dot: "var(--color-risk)", text: "var(--color-risk)" },
  rerouted: { bg: "var(--color-ok-soft)", dot: "var(--color-rerouted)", text: "var(--color-rerouted)" },
  delivered: { bg: "var(--color-tile)", dot: "var(--color-muted)", text: "var(--color-muted)" },
};

export function StatusChip({ status }: { status: DisplayStatus }) {
  const t = TONE[status];
  return (
    <span
      className="inline-flex h-4 items-center gap-[5px] whitespace-nowrap rounded-full pr-[8px] pl-[7px] text-[10.5px] leading-none font-bold"
      style={{ background: t.bg, color: t.text }}
    >
      {status === "delivered" ? (
        <span className="text-[9px]">✓</span>
      ) : (
        <span className="size-[5px] rounded-full" style={{ background: t.dot }} />
      )}
      {STATUS_LABEL[status]}
    </span>
  );
}
