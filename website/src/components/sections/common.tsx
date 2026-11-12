import type { GraphNode } from "@/lib/types";
import { shortNodeName } from "@/lib/format";

/** Каркас раздела: подзаголовок, заголовок, действия справа, прокрутка содержимого. */
export function SectionPage({
  kicker,
  title,
  subtitle,
  actions,
  children,
}: {
  kicker: string;
  title: string;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="scroll-thin relative min-w-0 flex-1 overflow-y-auto bg-bg px-8 pb-10">
      <div className="flex items-start justify-between gap-4 pt-[28px]">
        <div className="min-w-0">
          <div className="caps text-[10px] leading-[12px] font-bold text-muted">{kicker}</div>
          <h1 className="mt-[14px] text-[32px] leading-[40px] font-bold">{title}</h1>
          {subtitle && <p className="mt-[6px] text-[15px] leading-[20px] text-muted">{subtitle}</p>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-3">{actions}</div>}
      </div>
      <div className="mt-[24px]">{children}</div>
    </div>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`rounded-[12px] border border-line bg-panel ${className}`}>{children}</div>;
}

/** Таблица: заголовок колонок и строки на CSS-сетке (одна строка шаблона на всю таблицу). */
export function Table({ cols, head, children, minWidth = 960 }: {
  cols: string;
  head: React.ReactNode[];
  children: React.ReactNode;
  minWidth?: number;
}) {
  return (
    <Card className="overflow-hidden">
      <div className="scroll-thin overflow-x-auto">
        <div style={{ minWidth }}>
          <div
            className="caps grid h-[44px] items-center gap-x-4 border-b border-line px-[16px] text-[10px] font-bold text-muted"
            style={{ gridTemplateColumns: cols }}
          >
            {head.map((h, i) => (
              <span key={i} className="truncate">
                {h}
              </span>
            ))}
          </div>
          {children}
        </div>
      </div>
    </Card>
  );
}

export function Row({ cols, children, onClick, tone }: {
  cols: string;
  children: React.ReactNode;
  onClick?(): void;
  tone?: "risk";
}) {
  const cls = `grid min-h-[56px] w-full items-center gap-x-4 border-b border-line px-[16px] py-[8px] text-left text-[15px] last:border-b-0 ${
    tone === "risk" ? "bg-risk-soft" : ""
  } ${onClick ? "cursor-pointer transition-colors hover:bg-tile" : ""}`;
  return onClick ? (
    <button type="button" onClick={onClick} className={cls} style={{ gridTemplateColumns: cols }}>
      {children}
    </button>
  ) : (
    <div className={cls} style={{ gridTemplateColumns: cols }}>
      {children}
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="py-12 text-center text-[15px] text-muted">{children}</div>;
}

export function nodeName(nodes: Map<string, GraphNode>, id: string) {
  const n = nodes.get(id);
  return n ? shortNodeName(n.name) : id;
}

export function Pill({ children, tone }: { children: React.ReactNode; tone: "risk" | "ok" | "warn" | "info" | "muted" }) {
  const cls = {
    risk: "bg-risk-soft text-risk-text",
    ok: "bg-ok-soft text-rerouted-text",
    warn: "bg-warn-soft text-warn-text",
    info: "bg-info-soft text-transit-text",
    muted: "bg-tile text-muted",
  }[tone];
  return (
    <span className={`inline-flex h-[24px] items-center whitespace-nowrap rounded-full px-[10px] text-[12px] font-bold ${cls}`}>
      {children}
    </span>
  );
}

export const VIA_LABEL = { web: "через сайт", telegram: "через Telegram" } as const;
