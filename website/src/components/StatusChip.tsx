import { STATUS_LABEL } from "@/lib/derive";
import type { DisplayStatus } from "@/lib/types";

const TONE: Record<DisplayStatus, { bg: string; dot: string; text: string }> = {
  planned: { bg: "rgba(138,151,173,0.12)", dot: "#8A97AD", text: "#A9B4C6" },
  in_transit: { bg: "rgba(59,130,246,0.12)", dot: "#3B82F6", text: "#9DC8FF" },
  at_risk: { bg: "rgba(239,68,68,0.12)", dot: "#EF4444", text: "#FF888D" },
  rerouted: { bg: "rgba(34,197,94,0.12)", dot: "#22C55E", text: "#7EE2A2" },
  delivered: { bg: "rgba(138,151,173,0.12)", dot: "#8A97AD", text: "#C9D2E0" },
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
