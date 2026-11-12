"use client";

import { useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import { AuthScreen } from "@/components/AuthScreen";
import { isLoggedIn } from "@/lib/session";

const emptySubscribe = () => () => undefined;

export default function LoginPage() {
  const router = useRouter();
  const hydrated = useSyncExternalStore(emptySubscribe, () => true, () => false);
  const loggedIn = useSyncExternalStore(emptySubscribe, isLoggedIn, () => false);

  useEffect(() => {
    if (hydrated && loggedIn) router.replace("/");
  }, [hydrated, loggedIn, router]);

  if (!hydrated || loggedIn) {
    return <div className="flex h-full items-center justify-center bg-bg text-[13px] text-muted">Загрузка…</div>;
  }
  return <AuthScreen />;
}
