"use client";

import { useEffect, useState } from "react";

export type SiteTheme = "light" | "dark";

/**
 * Тема сайта — один вход для всех компонентов, которым она нужна в JS (подложка карты).
 *
 * Источник, по порядку:
 *  1. атрибут `data-theme="dark|light"` на <html> — его ставит переключатель темы сайта;
 *  2. класс `dark` / `light` на <html> — если переключатель работает классом;
 *  3. пока переключателя нет — системная тема (`prefers-color-scheme`).
 * Чтобы подключить переключатель, достаточно, чтобы он ставил `document.documentElement.dataset.theme`:
 * хук следит за атрибутом и классом на <html> и перерисовывает подписчиков.
 */
export function readSiteTheme(): SiteTheme {
  if (typeof document === "undefined") return "dark";
  const root = document.documentElement;
  const attr = root.dataset.theme;
  if (attr === "dark" || attr === "light") return attr;
  if (root.classList.contains("dark")) return "dark";
  if (root.classList.contains("light")) return "light";
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function useSiteTheme(): SiteTheme {
  const [theme, setTheme] = useState<SiteTheme>(() => readSiteTheme());
  useEffect(() => {
    const update = () => setTheme(readSiteTheme());
    const obs = new MutationObserver(update);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    mq?.addEventListener("change", update);
    update();
    return () => {
      obs.disconnect();
      mq?.removeEventListener("change", update);
    };
  }, []);
  return theme;
}
