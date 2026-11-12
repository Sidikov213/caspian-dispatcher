import { ROLE_LABEL } from "@/lib/session";
import { formatDateTime } from "@/lib/format";
import type { Alert } from "@/lib/types";

const VIA = { web: "через сайт", telegram: "через Telegram" } as const;
const cut = (t: string) => t.replace(/\s*\(.*\)\s*$/, "");

/** Статус решения по алерту — для экспедитора (вместо кнопок) и для закрытых алертов. */
export function AlertDecisionNote({ alert }: { alert: Alert }) {
  let title: string;
  let sub: string | null = null;
  let tone = "border-line bg-tile text-text";
  if (alert.status === "new") {
    title = "Решение принимает логист";
    sub = "Ждёт решения";
  } else if (alert.status === "accepted") {
    tone = "border-ok-line bg-ok-soft text-rerouted-text";
    const opt = alert.options.find((o) => o.recommended);
    title = `Принято: ${opt ? cut(opt.title) : "ждать следующий рейс"}`;
    const by = alert.accepted_by ? `${alert.accepted_by.name} (${ROLE_LABEL[alert.accepted_by.role].toLowerCase()})` : null;
    const via = alert.accepted_via ? VIA[alert.accepted_via] : null;
    sub = [by, via, alert.accepted_at ? formatDateTime(alert.accepted_at) : null].filter(Boolean).join(" · ");
  } else if (alert.status === "rejected") {
    tone = "border-warn-line bg-warn-soft text-warn-text";
    title = "Отклонено: груз ждёт следующий рейс";
  } else {
    title = "Алерт закрыт";
    sub = alert.status_note ?? "Предложение устарело";
  }
  return (
    <div className={`rounded-[12px] border px-[14px] py-[12px] ${tone}`}>
      <div className="text-[15px] leading-[20px] font-bold">{title}</div>
      {sub && <div className="mt-[4px] text-[13px] leading-[17px] text-muted">{sub}</div>}
      {alert.status !== "superseded" && alert.status_note && (
        <div className="mt-[4px] text-[13px] leading-[17px] text-muted">{alert.status_note}</div>
      )}
    </div>
  );
}
