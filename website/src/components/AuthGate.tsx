"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { clearSession, getStoredUser, getToken, setSession } from "@/lib/session";
/** Проверяет сессию и редиректит на /login, если токена нет или он недействителен. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const token = getToken();
      if (!token) {
        router.replace("/login");
        return;
      }
      const cached = getStoredUser();
      try {
        const me = await api.me(token);
        if (cancelled) return;
        setSession(token, me);
        setReady(true);
      } catch (e) {
        if (cancelled) return;
        // Нет сети к /auth/me — оставляем кэш, чтобы демо не вылетало; битый токен сбрасываем.
        if (e instanceof ApiError && (e.code === "invalid_token" || e.status === 401)) {
          clearSession();
          router.replace("/login");
          return;
        }
        if (cached) setReady(true);
        else router.replace("/login");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (!ready) {
    return (
      <div className="flex h-full items-center justify-center bg-bg text-[13px] text-muted">
        Проверяем сессию…
      </div>
    );
  }

  return <>{children}</>;
}
