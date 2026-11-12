"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { setSession } from "@/lib/session";
import type { AuthRole } from "@/lib/types";
import { AuthMap } from "./AuthMap";
import { LogoWordmark } from "./icons";

type Mode = "login" | "register";

const ROLE_TABS: { id: AuthRole; label: string }[] = [
  { id: "logist", label: "Логист" },
  { id: "expeditor", label: "Экспедист" },
];

const fieldClass =
  "h-11 w-full rounded-[8px] border border-line bg-panel px-3.5 text-[14px] text-text outline-none transition-[border-color,box-shadow] placeholder:text-faint focus:border-action focus:shadow-[0_0_0_3px_rgba(36,91,219,0.12)]";

function authErrorMessage(e: unknown) {
  if (!(e instanceof ApiError)) return "Не удалось выполнить запрос";
  switch (e.code) {
    case "email_taken":
      return "Этот email уже зарегистрирован";
    case "invalid_credentials":
      return "Неверный email или пароль";
    case "weak_password":
      return "Пароль должен быть не короче 6 символов";
    case "invalid_email":
      return "Проверьте формат email";
    case "validation_error":
      return e.message || "Проверьте заполненные поля";
    default:
      return e.message || "Ошибка авторизации";
  }
}

export function AuthScreen() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<AuthRole>("logist");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const out =
        mode === "login"
          ? await api.login({ email, password })
          : await api.register({ name, email, password, role });
      setSession(out.token, out.user);
      router.replace("/");
    } catch (err) {
      setError(authErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full min-h-[720px] bg-bg">
      <aside className="relative hidden min-w-0 flex-1 overflow-hidden border-r border-line lg:block">
        <AuthMap />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-bg/10 via-transparent to-bg/40" />
        <div className="absolute top-8 left-8 z-10 max-w-[360px] rounded-[12px] border border-line bg-panel/95 px-5 py-4 shadow-[0_16px_40px_rgba(18,48,74,0.12)] backdrop-blur-sm">
          <LogoWordmark height={36} />
          <p className="mt-3 text-[14px] leading-[20px] text-muted">
            Окно логиста коридора «Север–Юг»: карта, цифровые двойники и прогноз стыковок на 48 часов вперёд.
          </p>
        </div>
        <div className="absolute bottom-8 left-8 z-10 rounded-[8px] border border-line bg-panel/90 px-3 py-2 text-[11px] text-muted backdrop-blur-sm">
          Схема маршрутов · демо-данные
        </div>
      </aside>

      <main className="flex w-full flex-col justify-center px-6 py-10 sm:px-10 lg:w-[520px] lg:shrink-0 xl:w-[560px]">
        <div className="mx-auto w-full max-w-[400px]">
          <div className="mb-8 lg:hidden">
            <LogoWordmark height={34} />
          </div>

          <div className="mb-6 flex h-[42px] rounded-[12px] border border-line bg-tile p-[3px]">
            {(
              [
                ["login", "Вход"],
                ["register", "Регистрация"],
              ] as const
            ).map(([id, label]) => {
              const active = mode === id;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => {
                    setMode(id);
                    setError(null);
                  }}
                  className={`flex h-[34px] flex-1 items-center justify-center rounded-[8px] text-[13px] font-bold transition-colors ${
                    active ? "bg-panel text-text shadow-[0_1px_2px_rgba(18,48,74,0.08)]" : "text-muted hover:text-text"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>

          <h1 className="text-[28px] leading-[34px] font-bold tracking-[-0.01em]">
            {mode === "login" ? "Вход в диспетчер" : "Создать аккаунт"}
          </h1>
          <p className="mt-2 text-[13px] leading-[18px] text-muted">
            {mode === "login"
              ? "Демо: logist@demo.ru или expeditor@demo.ru, пароль demo123"
              : "ФИО, email, пароль и роль — логист или экспедист"}
          </p>

          <form onSubmit={submit} className="mt-7 space-y-4">
            {mode === "register" && (
              <>
                <Field label="ФИО" htmlFor="name">
                  <input
                    id="name"
                    required
                    autoComplete="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Иванов Иван Иванович"
                    className={fieldClass}
                  />
                </Field>

                <div>
                  <div className="mb-2 text-[12px] font-bold text-muted">Роль</div>
                  <div className="flex h-[42px] rounded-[12px] border border-line bg-tile p-[3px]">
                    {ROLE_TABS.map((tab) => {
                      const active = role === tab.id;
                      return (
                        <button
                          key={tab.id}
                          type="button"
                          onClick={() => setRole(tab.id)}
                          className={`flex h-[34px] flex-1 items-center justify-center rounded-[8px] text-[13px] font-bold transition-colors ${
                            active ? "bg-action text-white" : "text-muted hover:bg-panel hover:text-text"
                          }`}
                        >
                          {tab.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </>
            )}

            <Field label="Email" htmlFor="email">
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.ru"
                className={fieldClass}
              />
            </Field>

            <Field label="Пароль" htmlFor="password">
              <input
                id="password"
                type="password"
                required
                minLength={mode === "register" ? 6 : undefined}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={mode === "register" ? "Не меньше 6 символов" : "••••••••"}
                className={fieldClass}
              />
            </Field>

            {error && (
              <div className="rounded-[8px] border border-[#FECACA] bg-risk-soft px-3 py-2.5 text-[12.5px] font-semibold text-risk-text">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={busy}
              className="mt-2 flex h-[46px] w-full items-center justify-center rounded-[8px] bg-action text-[14px] font-bold text-white transition-colors hover:bg-action-hover disabled:opacity-60"
            >
              {busy ? "Отправляем…" : mode === "login" ? "Войти" : "Зарегистрироваться"}
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}

function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: React.ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="block">
      <span className="mb-2 block text-[12px] font-bold text-muted">{label}</span>
      {children}
    </label>
  );
}
