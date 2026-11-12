"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Graph, Shipment, Weather } from "@/lib/types";
import { RealMap } from "./RealMap";

/**
 * Карта на экране входа: та же RealMap, что на пульте, по данным /api/graph, /api/shipments и /api/weather
 * (ключ API у сайта есть и до входа). Только просмотр: клик по грузу ничего не открывает.
 */
export function LoginMap() {
  const [graph, setGraph] = useState<Graph | null>(null);
  const [shipments, setShipments] = useState<Shipment[]>([]);
  const [weather, setWeather] = useState<Weather | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.getGraph().then((g) => !cancelled && setGraph(g)).catch(() => undefined);
    api.getShipments().then((s) => !cancelled && setShipments(s)).catch(() => undefined);
    api.getWeather().then((w) => !cancelled && setWeather(w)).catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const nodes = useMemo(() => new Map((graph?.nodes ?? []).map((n) => [n.id, n])), [graph]);
  const edges = useMemo(() => new Map((graph?.edges ?? []).map((e) => [e.id, e])), [graph]);

  if (!graph) return <div className="h-full w-full bg-map-sea" />;
  return (
    <RealMap
      nodes={nodes}
      edges={edges}
      shipments={shipments}
      weather={weather}
      focusId={null}
      insetRight={0}
      freshness={null}
      onSelect={() => undefined}
    />
  );
}
