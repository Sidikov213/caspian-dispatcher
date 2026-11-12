"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatDecimal, formatInt } from "@/lib/format";
import type { ModelInfo } from "@/lib/types";
import { Card, Pill, SectionPage } from "./common";

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card className="px-[20px] py-[16px]">
      <div className="caps text-[10px] font-bold text-muted">{label}</div>
      <div className="tnum mt-[8px] text-[32px] leading-[36px] font-bold">{value}</div>
      {hint && <div className="mt-[6px] text-[13px] text-muted">{hint}</div>}
    </Card>
  );
}

export function ModelSection() {
  const [info, setInfo] = useState<ModelInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getModel().then(setInfo, (e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const top = info ? Math.max(...info.feature_importance.map((f) => f.importance), 1e-9) : 1;
  const c = info?.classifier;

  return (
    <SectionPage
      kicker="Прогноз / Предиктор срыва стыковки"
      title="Модель"
      subtitle={info?.summary ?? (error ? null : "Загружаем сведения о модели…")}
      actions={info?.synthetic && <Pill tone="warn">Обучена на синтетической истории</Pill>}
    >
      {error && <Card className="px-[20px] py-[16px] text-[15px] text-muted">{error}</Card>}
      {info && (
        <>
          <div className="grid grid-cols-4 gap-[16px]">
            <Metric
              label="Активный предиктор"
              value={info.active === "catboost" ? "CatBoost" : "Формула"}
              hint={info.fallback_reason ?? `запрошен: ${info.requested}`}
            />
            <Metric label="AUC" value={c ? formatDecimal(c.auc, 3) : "—"} hint="на отложенной выборке" />
            <Metric label="Brier" value={c ? formatDecimal(c.brier, 3) : "—"} hint="ниже — точнее вероятности" />
            <Metric
              label="Выборка"
              value={c ? formatInt(c.n_train + c.n_test) : "—"}
              hint={c ? `обучение ${formatInt(c.n_train)} · проверка ${formatInt(c.n_test)}` : undefined}
            />
          </div>

          <div className="mt-[16px] grid grid-cols-[1.1fr_1fr] gap-[16px]">
            <Card className="px-[20px] py-[20px]">
              <h2 className="text-[18px] font-bold">Важность признаков</h2>
              <p className="mt-[4px] text-[14px] text-muted">Вклад признаков в классификатор CatBoost</p>
              <div className="mt-[20px] flex flex-col gap-[14px]">
                {info.feature_importance.map((f) => (
                  <div key={f.name}>
                    <div className="flex justify-between text-[15px]">
                      <span>{f.label}</span>
                      <span className="tnum text-muted">{formatDecimal(f.importance, 1)}</span>
                    </div>
                    <div className="mt-[6px] h-[8px] overflow-hidden rounded-full bg-tile">
                      <div className="h-full rounded-full bg-cyan" style={{ width: `${(f.importance / top) * 100}%` }} />
                    </div>
                  </div>
                ))}
                {info.feature_importance.length === 0 && <div className="text-[15px] text-muted">Нет данных о признаках</div>}
              </div>
            </Card>
            <Card className="px-[20px] py-[20px]">
              <h2 className="text-[18px] font-bold">Калибровка</h2>
              <p className="mt-[4px] text-[14px] text-muted">Предсказанная вероятность срыва против доли срывов</p>
              {/* eslint-disable-next-line @next/next/no-img-element -- статический экспорт, картинка из public/ */}
              <img
                src="/model_calibration.png"
                alt="График калибровки модели: предсказанная вероятность против наблюдаемой доли срывов"
                className="mt-[16px] w-full rounded-[8px] bg-white"
              />
            </Card>
          </div>

          <Card className="mt-[16px] px-[20px] py-[16px] text-[15px] leading-[22px] text-muted">
            {info.note}
            {info.regressor && (
              <span className="block">
                Регрессор сдвига отправления — только проверка: MAE {formatDecimal(info.regressor.mae_h, 1)}&nbsp;ч. На сервере сдвиг и
                задержки считает код по прогнозу погоды и расписанию.
              </span>
            )}
            {info.trained_at && <span className="block">Обучена {info.trained_at.slice(0, 10)}, seed {info.seed}.</span>}
          </Card>
        </>
      )}
    </SectionPage>
  );
}
