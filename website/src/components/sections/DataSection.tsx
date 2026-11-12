"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatDateTime, formatDecimal, formatInt } from "@/lib/format";
import type { DataSourceType, DataSources } from "@/lib/types";
import { Card, Empty, Pill, Row, SectionPage, Table } from "./common";

const TYPE: Record<DataSourceType, { label: string; tone: "ok" | "warn" | "muted" }> = {
  real: { label: "настоящие", tone: "ok" },
  modeled: { label: "смоделированы", tone: "warn" },
  synthetic: { label: "синтетика", tone: "muted" },
};
const PORT_NAME: Record<string, string> = { astrakhan: "Астрахань", olya: "Оля", makhachkala: "Махачкала" };
const COLS = "minmax(180px,1fr) 150px minmax(320px,2.4fr) 150px 120px";

function host(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function when(v: string | null) {
  if (!v) return "—";
  return v.length > 10 ? formatDateTime(v) : v.split("-").reverse().join(".");
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <div className="caps text-[10px] font-bold text-muted">{label}</div>
      <div className="tnum mt-[6px] text-[28px] leading-[32px] font-bold">{value}</div>
      {hint && <div className="mt-[4px] text-[13px] text-muted">{hint}</div>}
    </div>
  );
}

export function DataSection() {
  const [data, setData] = useState<DataSources | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.getDataSources().then(setData, (e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);
  const bt = data?.backtest;

  return (
    <SectionPage
      kicker="Данные / Откуда цифры"
      title="Данные"
      subtitle="Что в системе настоящее, что смоделировано для демо и что сгенерировано"
    >
      {error && <Card className="px-[20px] py-[16px] text-[15px] text-muted">{error}</Card>}
      {data && (
        <>
          <Table cols={COLS} head={["Источник", "Тип", "Что даёт", "Обновлено", "Ссылка"]} minWidth={1060}>
            {data.sources.length === 0 && <Empty>Источников нет</Empty>}
            {data.sources.map((s) => (
              <Row key={s.id} cols={COLS}>
                <span className="font-bold">{s.title}</span>
                <span>
                  <Pill tone={TYPE[s.type].tone}>{TYPE[s.type].label}</Pill>
                </span>
                <span className="text-[14px] leading-[19px]">
                  {s.provides}
                  {s.note && <span className="mt-[2px] block text-[13px] text-muted">{s.note}</span>}
                </span>
                <span className="tnum text-[14px] text-muted">{when(s.updated_at)}</span>
                <span className="min-w-0 text-[13px]">
                  {(s.urls?.length ? s.urls : s.url ? [s.url] : []).map((u) => (
                    <a key={u} href={u} target="_blank" rel="noreferrer" className="block truncate text-transit-text hover:underline">
                      {host(u)}
                    </a>
                  ))}
                  {!s.url && !s.urls?.length && <span className="text-muted">—</span>}
                </span>
              </Row>
            ))}
          </Table>

          {data.ice && (
            <Card className="mt-[16px] px-[20px] py-[20px]">
              <div className="flex items-start justify-between gap-4">
                <h2 className="text-[18px] font-bold">{data.ice.title}</h2>
                <Pill tone="warn">лёд — смоделирован</Pill>
              </div>
              {data.ice.conclusion && <p className="mt-[10px] text-[15px] leading-[21px]">{data.ice.conclusion}</p>}
              <ul className="mt-[12px] grid grid-cols-2 gap-x-[24px] gap-y-[8px] text-[14px] leading-[19px]">
                {data.ice.facts.map((f) => (
                  <li key={f.text} className="flex gap-[8px]">
                    <span className="mt-[7px] size-[5px] shrink-0 rounded-full bg-transit" />
                    <span>
                      {f.text}
                      {f.source ? (
                        <a href={f.source} target="_blank" rel="noreferrer" className="ml-[6px] text-[12px] text-transit-text hover:underline">
                          {host(f.source)}
                        </a>
                      ) : (
                        <span className="ml-[6px] text-[12px] text-muted">источник уточняется</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-[12px] text-[13px] text-warn-text">{data.ice.note}</p>
            </Card>
          )}

          <div className="mt-[16px] grid grid-cols-[1fr_2fr] gap-[16px]">
            <Card className="px-[20px] py-[20px]">
              <h2 className="text-[18px] font-bold">Коридор «Север–Юг» в 2025 году</h2>
              <ul className="mt-[14px] flex flex-col gap-[10px] text-[15px] leading-[20px]">
                {data.corridor_facts.map((f) => (
                  <li key={f.text} className="flex gap-[8px]">
                    <span className="mt-[8px] size-[5px] shrink-0 rounded-full bg-rerouted" />
                    {f.text}
                  </li>
                ))}
              </ul>
              {data.corridor_facts[0] && (
                <div className="mt-[14px] text-[12px] text-muted">
                  Источник:{" "}
                  <a href={data.corridor_facts[0].source} target="_blank" rel="noreferrer" className="text-transit-text hover:underline">
                    {host(data.corridor_facts[0].source)}
                  </a>
                </div>
              )}
            </Card>

            <Card className="px-[20px] py-[20px]">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2 className="text-[18px] font-bold">Ретроспективная симуляция на исторической погоде</h2>
                  <p className="mt-[4px] text-[14px] text-muted">
                    {bt ? `Погода настоящая, рейсы условные · ${bt.period.start} — ${bt.period.end}` : "Симуляция ещё не запускалась"}
                  </p>
                </div>
                {bt && <Pill tone="ok">волна — настоящая</Pill>}
              </div>
              {bt && (
                <>
                  <div className="mt-[16px] grid grid-cols-4 gap-[16px]">
                    <Stat label="Условных рейсов" value={formatInt(bt.sailings.departures)} hint="Астрахань, раз в 48 ч" />
                    <Stat label="В закрытое окно" value={formatInt(bt.sailings.closed)} hint={`волна ≥ ${formatDecimal(bt.wave_limit_m)} м`} />
                    <Stat label="Спас обход" value={formatInt(bt.sailings.saved_by_makhachkala)} hint="через Махачкалу" />
                    <Stat
                      label="Нет данных о волне"
                      value={formatInt(bt.sailings.no_data)}
                      hint={`Махачкала открыта в ${formatInt(bt.sailings.no_data_makhachkala_open)}`}
                    />
                  </div>
                  <div className="mt-[16px] grid grid-cols-3 gap-[12px]">
                    {Object.entries(bt.ports).map(([id, p]) => (
                      <div key={id} className="rounded-[8px] border border-line px-[12px] py-[10px] text-[13px] leading-[19px]">
                        <div className="text-[15px] font-bold">{PORT_NAME[id] ?? id}</div>
                        <div className="text-muted">
                          окон закрытия: <b className="text-text">{p.windows}</b>, часов: <b className="text-text">{p.closed_hours}</b>
                        </div>
                        <div className="text-muted">
                          максимум волны: <b className="text-text">{p.max_wave_m === null ? "—" : `${formatDecimal(p.max_wave_m, 2)} м`}</b>
                        </div>
                        <div className="text-muted">
                          без данных: <b className="text-text">{formatInt(p.hours_no_data)} ч</b>
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="mt-[12px] text-[13px] leading-[18px] text-muted">{bt.note}</p>
                </>
              )}
            </Card>
          </div>

          {bt && (
            <Card className="mt-[16px] p-[16px]">
              {/* eslint-disable-next-line @next/next/no-img-element -- статический экспорт, картинка из public/ */}
              <img
                src={bt.chart}
                alt="Высота волны за 12 месяцев у Астрахани, Оли и Махачкалы с пределом парома 2,5 м"
                className="w-full rounded-[8px] bg-white"
              />
            </Card>
          )}
        </>
      )}
    </SectionPage>
  );
}
