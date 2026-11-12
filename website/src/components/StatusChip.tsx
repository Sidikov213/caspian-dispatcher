import { STATUS_LABEL } from "@/lib/derive";
import type { DisplayStatus } from "@/lib/types";

/** Светлые подложки статусов: бриф (красная / жёлтая / зелёная / синяя). */
const TONE: Record<DisplayStatus, { bg: string; dot: string; text: string }> = {
  planned: { bg: "#F1F5F9", dot: "#64748B", text: "#64748B" },
  in_transit: { bg: "#EFF6FF", dot: "#245BDB", text: "#245BDB" },
  at_risk: { bg: "#FEF2F2", dot: "#DC2626", text: "#DC2626" },
  rerouted: { bg: "#F0FDF4", dot: "#15803D", text: "#15803D" },
  delivered: { bg: "#F1F5F9", dot: "#64748B", text: "#64748B" },
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
