"""Граф маршрутов на networkx: узлы и рёбра из seed.json.

Граф ориентированный (рёбра в сиде заданы «откуда → куда»). Поиск альтернатив — простые пути
по возрастанию base_hours без заблокированных рёбер; время в узлах и рейсы считает schedule.py.
Часы, стоимость и CO₂ — по рёбрам: ₽ = cost_rub_per_t × т, CO₂ = т × км × г/т·км / 1000.
В продакшене — графовая БД.
"""
from itertools import islice

import networkx as nx

# Каспийский паром: рёбра моря, на которые нужен рейс из расписания. Остальные морские — океан.
KIND_FERRY, KIND_OCEAN = "ferry", "ocean"


class Graph:
    def __init__(self, nodes: list[dict], edges: list[dict], ferry_edges: list[str]):
        self.nodes = {n["id"]: n for n in nodes}
        self.edges = {e["id"]: e for e in edges}
        self.ferry_edges = set(ferry_edges)
        self.G = nx.DiGraph()
        for n in nodes:
            self.G.add_node(n["id"])
        for e in edges:
            self.G.add_edge(e["from"], e["to"], id=e["id"], base_hours=e["base_hours"])

    def to_api(self) -> dict:
        return {"nodes": list(self.nodes.values()), "edges": list(self.edges.values())}

    def kind(self, eid: str) -> str:
        e = self.edges[eid]
        if e["mode"] == "sea":
            return KIND_FERRY if eid in self.ferry_edges else KIND_OCEAN
        return e["mode"]

    def paths(self, src: str, dst: str, banned: set[str] = frozenset(), limit: int = 8) -> list[list[str]]:
        """До `limit` простых путей src → dst (списки id рёбер) без рёбер из banned."""
        if src == dst or src not in self.G or dst not in self.G:
            return []
        view = nx.subgraph_view(self.G, filter_edge=lambda u, v: self.G[u][v]["id"] not in banned)
        try:
            gen = nx.shortest_simple_paths(view, src, dst, weight="base_hours")
            return [[self.G[u][v]["id"] for u, v in zip(p, p[1:])] for p in islice(gen, limit)]
        except nx.NetworkXNoPath:
            return []

    def cost_rub(self, eids, weight_t: float) -> float:
        return sum(self.edges[e]["cost_rub_per_t"] for e in eids) * weight_t

    def co2_kg(self, eids, weight_t: float) -> float:
        return sum(weight_t * self.edges[e]["distance_km"] * self.edges[e]["co2_g_per_tkm"] / 1000
                   for e in eids)

    def branch(self, eids) -> str:
        branches = {self.edges[e]["branch"] for e in eids}
        for b in ("west", "east"):
            if b in branches:
                return b
        return "transcaspian"
