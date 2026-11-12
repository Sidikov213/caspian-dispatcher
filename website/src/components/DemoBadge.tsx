/** Плашка «Демо-стенд»: в шапке — с подсказкой при наведении, на экране входа — с подписью рядом. */
export const DEMO_HINT = "Данные учебные и общие для всех пользователей";

export function DemoBadge({ withHint = false, hanging = false }: { withHint?: boolean; hanging?: boolean }) {
  return (
    <span className="inline-flex items-center gap-[9px]" title={DEMO_HINT}>
      <span
        className={`caps inline-flex shrink-0 cursor-help items-center gap-[6px] border px-[9px] leading-none font-bold whitespace-nowrap ${
          hanging ? "h-[19px] rounded-b-[7px] border-t-0 text-[9.5px]" : "h-[24px] rounded-[7px] text-[10.5px]"
        }`}
        style={{ borderColor: "var(--color-warn-line)", background: "var(--color-warn-soft)", color: "var(--color-warn-text)" }}
      >
        <span aria-hidden className="size-[6px] rounded-full" style={{ background: "var(--color-warn)" }} />
        Демо-стенд
      </span>
      {withHint ? (
        <span className="text-[12px] leading-[16px] text-muted">{DEMO_HINT}</span>
      ) : (
        <span className="sr-only">{DEMO_HINT}</span>
      )}
    </span>
  );
}
