// Единые подписи — CLAUDE.md, раздел 9. Время сценария московское (UTC+3, без перехода на летнее).

const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
const MSK_OFFSET_MS = 3 * 3600 * 1000;
const NBSP = "\u00A0";

function msk(ts: string | number | Date): Date {
  return new Date(new Date(ts).getTime() + MSK_OFFSET_MS);
}

const pad = (n: number) => String(n).padStart(2, "0");

/** «12 ноя, 14:30» */
export function formatDateTime(ts: string): string {
  const d = msk(ts);
  return `${d.getUTCDate()}${NBSP}${MONTHS[d.getUTCMonth()]}, ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

/** «14:30» */
export function formatTime(ts: string): string {
  const d = msk(ts);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

export function sameMskDay(a: string, b: string): boolean {
  const x = msk(a);
  const y = msk(b);
  return x.getUTCFullYear() === y.getUTCFullYear() && x.getUTCMonth() === y.getUTCMonth() && x.getUTCDate() === y.getUTCDate();
}

export function addHours(ts: string, hours: number): string {
  return new Date(new Date(ts).getTime() + hours * 3600 * 1000).toISOString();
}

/** Целое с неразрывными пробелами между разрядами: «2 460». */
export function formatInt(n: number): string {
  const s = String(Math.round(Math.abs(n))).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  return n < 0 ? `−${s}` : s;
}

/** Десятичная запятая: «1,2». */
export function formatDecimal(n: number, digits = 1): string {
  const s = Math.abs(n).toFixed(digits).replace(".", ",");
  return n < 0 ? `−${s}` : s;
}

/** «+18 ч», «0 ч». */
export function formatHoursDelta(h: number): string {
  const v = Math.round(h);
  if (v === 0) return `0${NBSP}ч`;
  return `${v > 0 ? "+" : "−"}${formatInt(Math.abs(v))}${NBSP}ч`;
}

/** «298 тыс ₽», «1,2 млн ₽», «0 ₽». */
export function formatRub(n: number): string {
  const a = Math.abs(n);
  if (a >= 1_000_000) return `${formatDecimal(n / 1_000_000)}${NBSP}млн${NBSP}₽`;
  if (a >= 1_000) return `${formatInt(Math.round(n / 1000))}${NBSP}тыс${NBSP}₽`;
  return `${formatInt(n)}${NBSP}₽`;
}

/** «82%» */
export function formatPercent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

/** «−6,7%», «0%» */
export function formatSignedPct(pct: number): string {
  if (Math.abs(pct) < 0.05) return "0%";
  return `${pct < 0 ? "−" : "+"}${formatDecimal(Math.abs(pct))}%`;
}

/** «№01» из «sh-01». */
export function shipmentNumber(id: string): string {
  const m = id.match(/(\d+)$/);
  return `№${m ? m[1].padStart(2, "0") : id}`;
}

export function shipmentIndex(id: string): number {
  const m = id.match(/(\d+)$/);
  return m ? Number(m[1]) : 0;
}

/** Короткое имя узла для подписей: «Мумбаи (Нава-Шева)» → «Мумбаи», «Баку / Алят» → «Баку». */
export function shortNodeName(name: string): string {
  return name.replace(/\s*\(.*\)\s*$/, "").replace(/\s*\/.*$/, "").trim();
}

export function minutesAgo(ts: string, now: number): number {
  return Math.max(0, Math.round((now - new Date(ts).getTime()) / 60000));
}
