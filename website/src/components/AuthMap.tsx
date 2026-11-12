"use client";

import { useLayoutEffect, useRef, useState } from "react";
import { BORDERS, CASPIAN, CASPIAN_CONTOURS, INLAND_SEA, LAND } from "@/lib/map/geometry";
import {
  COUNTRY_LABELS,
  DEFAULT_VIEW,
  GRID_DX,
  GRID_DY,
  GRID_Y0,
  NODE_LABELS,
  bezierPath,
  edgeGeometry,
  nodePos,
  type Pt,
} from "@/lib/map/layout";

/** Косметическая схема коридора для экрана входа — та же геометрия, без интерактива. */
const DEMO_EDGES = [
  "e-moscow-astrakhan",
  "e-astrakhan-anzali",
  "e-anzali-rasht",
  "e-rasht-tehran",
  "e-tehran-bandar_abbas",
  "e-bandar_abbas-mumbai",
  "e-astrakhan-makhachkala",
  "e-makhachkala-anzali",
] as const;

const ROUTE = { rail: "#245BDB", sea: "#087F8C", road: "#15803D", casing: "#E2E8F0" };

function dash(mode: "rail" | "sea" | "road", k: number) {
  if (mode === "sea") return { dasharray: `${7 * k} ${5 * k}`, cap: "butt" as const };
  if (mode === "road") return { dasharray: `${0.01 * k} ${5.2 * k}`, cap: "round" as const };
  return { cap: "round" as const };
}

export function AuthMap() {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const pad = 24;
  const s =
    size.w > 0
      ? Math.min((size.w - pad * 2) / DEFAULT_VIEW.w, (size.h - pad * 2) / DEFAULT_VIEW.h)
      : 1;
  const tx = size.w / 2 - (DEFAULT_VIEW.x + DEFAULT_VIEW.w / 2) * s;
  const ty = size.h / 2 - (DEFAULT_VIEW.y + DEFAULT_VIEW.h / 2) * s;
  const k = 1 / Math.max(s, 0.001);
  const toScreen = (p: Pt): Pt => [p[0] * s + tx, p[1] * s + ty];

  const paths = DEMO_EDGES.flatMap((id) => {
    const fromTo: Record<string, { from: string; to: string; mode: "rail" | "sea" | "road" }> = {
      "e-moscow-astrakhan": { from: "moscow", to: "astrakhan", mode: "rail" },
      "e-astrakhan-anzali": { from: "astrakhan", to: "anzali", mode: "sea" },
      "e-anzali-rasht": { from: "anzali", to: "rasht", mode: "road" },
      "e-rasht-tehran": { from: "rasht", to: "tehran", mode: "road" },
      "e-tehran-bandar_abbas": { from: "tehran", to: "bandar_abbas", mode: "road" },
      "e-bandar_abbas-mumbai": { from: "bandar_abbas", to: "mumbai", mode: "sea" },
      "e-astrakhan-makhachkala": { from: "astrakhan", to: "makhachkala", mode: "rail" },
      "e-makhachkala-anzali": { from: "makhachkala", to: "anzali", mode: "sea" },
    };
    const meta = fromTo[id];
    const g = edgeGeometry({ id, from: meta.from, to: meta.to });
    return g ? [{ id, d: bezierPath(g), mode: meta.mode }] : [];
  });

  return (
    <div ref={ref} className="absolute inset-0 overflow-hidden bg-bg" aria-hidden>
      <svg className="absolute inset-0 size-full">
        <g transform={`matrix(${s} 0 0 ${s} ${tx} ${ty})`}>
          <path d={LAND} fill="#E8EEF5" stroke="#CDD7E4" strokeWidth={1.1 * k} strokeLinejoin="round" />
          <path d={INLAND_SEA} fill="#D5E4F0" stroke="#B7CADA" strokeWidth={1.1 * k} />
          <path d={CASPIAN} fill="#C5DBEC" stroke="#8FB0C8" strokeWidth={1.2 * k} strokeLinejoin="round" />
          {CASPIAN_CONTOURS.map((d, i) => (
            <path key={i} d={d} fill="none" stroke="rgba(8,127,140,0.18)" strokeWidth={1 * k} strokeLinejoin="round" />
          ))}
          {BORDERS.map((d, i) => (
            <path
              key={i}
              d={d}
              fill="none"
              stroke="#A8B8C9"
              strokeWidth={1.1 * k}
              strokeDasharray={`${2.6 * k} ${3.4 * k}`}
              strokeLinejoin="round"
            />
          ))}
          <Grid k={k} />
          {paths.map((r) => (
            <path key={`${r.id}-c`} d={r.d} fill="none" stroke={ROUTE.casing} strokeWidth={7 * k} strokeLinecap="round" strokeLinejoin="round" />
          ))}
          {paths.map((r) => {
            const st = dash(r.mode, k);
            return (
              <path
                key={r.id}
                d={r.d}
                fill="none"
                stroke={ROUTE[r.mode]}
                strokeWidth={(r.mode === "road" ? 3.2 : 2.6) * k}
                strokeDasharray={st.dasharray}
                strokeLinecap={st.cap}
                strokeLinejoin="round"
              />
            );
          })}
        </g>

        {COUNTRY_LABELS.map((c) => {
          const [x, y] = toScreen([c.x, c.y]);
          return (
            <text
              key={c.text.join(" ")}
              x={x}
              y={y}
              textAnchor={c.anchor}
              dominantBaseline="central"
              fill={c.sea ? "#087F8C" : "#64748B"}
              fontSize={c.sea ? 11 : 9.5}
              fontWeight={700}
              letterSpacing={c.sea ? "0.2em" : "0.16em"}
            >
              {c.text.map((t, i) => (
                <tspan key={t} x={x} dy={i === 0 ? 0 : 17}>
                  {t}
                </tspan>
              ))}
            </text>
          );
        })}

        {Object.entries(NODE_LABELS).map(([id, label]) => {
          const p = nodePos(id);
          if (!p) return null;
          const [x, y] = toScreen(p);
          return (
            <g key={id}>
              <circle cx={x} cy={y} r={4.6} fill="#FFFFFF" stroke="#12304A" strokeWidth={1.8} />
              <text x={x + label.dx} y={y + label.dy} textAnchor={label.anchor} dominantBaseline="central" fill="#12304A" fontSize={11} fontWeight={700}>
                {id === "bandar_abbas" ? "Бендер-Аббас" : id === "mumbai" ? "Мумбаи" : id === "makhachkala" ? "Махачкала" : id === "astrakhan" ? "Астрахань" : id === "moscow" ? "Москва" : id === "anzali" ? "Энзели" : id === "baku" ? "Баку" : id === "samara" ? "Самара" : id === "saratov" ? "Саратов" : id}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function Grid({ k }: { k: number }) {
  const lines: React.ReactNode[] = [];
  const x0 = -3000;
  const x1 = 4000;
  const y0 = -3000;
  const y1 = 3800;
  for (let x = Math.ceil(x0 / GRID_DX) * GRID_DX; x <= x1; x += GRID_DX) {
    lines.push(<line key={`x${x}`} x1={x} y1={y0} x2={x} y2={y1} />);
  }
  for (let y = GRID_Y0 + Math.ceil((y0 - GRID_Y0) / GRID_DY) * GRID_DY; y <= y1; y += GRID_DY) {
    lines.push(<line key={`y${y}`} x1={x0} y1={y} x2={x1} y2={y} />);
  }
  return (
    <g stroke="rgba(18,48,74,0.06)" strokeWidth={1.6 * k}>
      {lines}
    </g>
  );
}
