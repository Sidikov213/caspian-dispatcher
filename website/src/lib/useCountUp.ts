"use client";

import { useEffect, useRef, useState } from "react";

function reducedMotion(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Число «добегает» от прежнего значения до нового за `ms`. Только показ: само значение приходит с сервера,
 * в конце на экране ровно оно. Анимация идёт, когда значение растёт по модулю (приняли решение);
 * уменьшение (сброс демо) и «уменьшить движение» — сразу новое значение, без анимации.
 * flash увеличивается на 1 в конце каждого добега — по нему один раз включается подсветка.
 */
export function useCountUp(target: number, ms = 1000): { value: number; flash: number } {
  const [anim, setAnim] = useState<{ value: number; to: number } | null>(null);
  const [flash, setFlash] = useState(0);
  const shown = useRef(target);

  useEffect(() => {
    const from = shown.current;
    if (from === target) return;
    if (Math.abs(target) <= Math.abs(from) || reducedMotion()) {
      shown.current = target;
      return;
    }
    let raf = 0;
    let start: number | null = null;
    const step = (now: number) => {
      if (start === null) start = now;
      const t = Math.min(1, (now - start) / ms);
      if (t >= 1) {
        shown.current = target;
        setAnim(null);
        setFlash((n) => n + 1);
        return;
      }
      const eased = 1 - Math.pow(1 - t, 3);
      const value = from + (target - from) * eased;
      shown.current = value;
      setAnim({ value, to: target });
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);

  // незавершённый добег к прежней цели не показываем: на экране сразу новое значение
  return { value: anim && anim.to === target ? anim.value : target, flash };
}
