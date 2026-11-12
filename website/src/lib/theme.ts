"use client";

import { useEffect, useState } from "react";

export type SiteTheme = "light" | "dark";

export const THEME_KEY = "caspian.theme";

/** Скрипт в <head>: ставит тему до отрисовки, чтобы не мигало. Тёмная — по умолчанию. */
export const THEME_BOOT = `try{var t=localStorage.getItem("${"caspian.theme"}");document.documentElement.dataset.theme=t==="light"?"light":"dark"}catch(e){document.documentElement.dataset.theme="dark"}`;

/**
 * Тема сайта — один вход для всех компонентов, которым она нужна в JS (подложка карты).
 * Источник — атрибут `data-theme="dark|light"` на <html>; его ставит переключатель в шапке (и скрипт
 * в <head> при загрузке). Без атрибута — тёмная.
 */
export function readSiteTheme(): SiteTheme {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

export function setSiteTheme(theme: SiteTheme) {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // приватный режим — выбор живёт до перезагрузки
  }
}

export function useSiteTheme(): SiteTheme {
  const [theme, setTheme] = useState<SiteTheme>(() => readSiteTheme());
  useEffect(() => {
    const update = () => setTheme(readSiteTheme());
    const obs = new MutationObserver(update);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    update();
    return () => obs.disconnect();
  }, []);
  return theme;
}
