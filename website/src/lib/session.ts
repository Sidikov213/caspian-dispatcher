import { useEffect, useState } from "react";
import type { AuthUser, Permission } from "./types";

const SESSION_EVENT = "caspian:session";

const TOKEN_KEY = "caspian.auth.token";
const USER_KEY = "caspian.auth.user";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function setSession(token: string, user: AuthUser) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  window.dispatchEvent(new Event(SESSION_EVENT));
}

/** Право из /api/auth/me. Клиент права из роли не выводит: нет в списке — нет права. */
export function can(user: AuthUser | null, permission: Permission): boolean {
  return !!user?.permissions?.includes(permission);
}

export const ROLE_LABEL: Record<AuthUser["role"], string> = { logist: "Логист", expeditor: "Экспедитор" };

/** Текущий пользователь; обновляется, когда AuthGate получил свежий /auth/me. */
export function useSessionUser(): AuthUser | null {
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser());
  useEffect(() => {
    const update = () => setUser(getStoredUser());
    window.addEventListener(SESSION_EVENT, update);
    window.addEventListener("storage", update);
    return () => {
      window.removeEventListener(SESSION_EVENT, update);
      window.removeEventListener("storage", update);
    };
  }, []);
  return user;
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function isLoggedIn() {
  return !!getToken();
}
