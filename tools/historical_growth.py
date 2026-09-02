#!/usr/bin/env python3
"""Deterministic causal town-growth simulator used by Experiment 005.

Inputs describe causes, phase rules, semantic programs, constraints, and a seed.
They deliberately contain no map coordinates.  The simulator produces persistent
semantic nodes, routes, districts, plots, building instances, surfaces, props,
vegetation zones, and an entry route that an RPG-Cobo compiler can execute.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from copy import deepcopy
from typing import Any, Iterable


FORBIDDEN_BRIEF_KEYS = {
    "x",
    "y",
    "z",
    "anchor",
    "center",
    "position",
    "point",
    "points",
    "start",
    "end",
    "endpoint",
    "endpoints",
    "rect",
    "rectangle",
    "coordinates",
}


def validate_non_spatial_brief(value: Any, path: str = "brief") -> None:
    """Reject authored spatial instructions while allowing sizes and constraints."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in FORBIDDEN_BRIEF_KEYS:
                raise ValueError(f"Spatial key {path}.{key} is forbidden in a causal brief")
            validate_non_spatial_brief(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_non_spatial_brief(item, f"{path}[{index}]")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def distance(a: Iterable[float], b: Iterable[float]) -> float:
    ax, az = a
    bx, bz = b
    return math.hypot(ax - bx, az - bz)


def interpolate(a: Iterable[float], b: Iterable[float], amount: float) -> tuple[float, float]:
    ax, az = a
    bx, bz = b
    return ax + (bx - ax) * amount, az + (bz - az) * amount


def nearest_on_segment(
    point: Iterable[float], start: Iterable[float], end: Iterable[float]
) -> tuple[tuple[float, float], float]:
    px, pz = point
    ax, az = start
    bx, bz = end
    dx, dz = bx - ax, bz - az
    length_sq = dx * dx + dz * dz
    if length_sq == 0:
        return (ax, az), distance(point, start)
    amount = clamp(((px - ax) * dx + (pz - az) * dz) / length_sq, 0.0, 1.0)
    nearest = (ax + dx * amount, az + dz * amount)
    return nearest, distance(point, nearest)


def rects_overlap(a: list[int], b: list[int], clearance: int = 0) -> bool:
    ax, az, aw, ad = a
    bx, bz, bw, bd = b
    return not (
        ax + aw + clearance <= bx
        or bx + bw + clearance <= ax
        or az + ad + clearance <= bz
        or bz + bd + clearance <= az
    )


def rect_center(rect: list[int]) -> tuple[float, float]:
    return rect[0] + rect[2] / 2, rect[1] + rect[3] / 2


def angle_bin(start: list[int], end: list[int], degrees: int = 15) -> int:
    angle = (math.degrees(math.atan2(end[1] - start[1], end[0] - start[0])) + 180) % 180
    return round(angle / degrees)


class HistoricalGrowthSimulator:
    """Compile a compact causal brief into a persistent semantic town plan."""

    def __init__(
        self,
        brief: dict[str, Any],
        shared_constraints: dict[str, Any],
        asset_sizes: dict[str, list[int]],
    ):
        validate_non_spatial_brief(brief)
        self.brief = deepcopy(brief)
        self.constraints = deepcopy(shared_constraints)
        self.asset_sizes = deepcopy(asset_sizes)
        self.width, self.height, self.depth = self.constraints["map_size"]
        self.margin = int(self.constraints["edge_margin_blocks"])
        self.clearance = int(self.constraints["building_clearance_blocks"])
        self.rng = random.Random(int(brief["seed"]))
        self._counters: dict[str, int] = {}
        self.plan: dict[str, Any] = {
            "schema": "rpgcobo.ai-native.generated-town-plan.v1",
            "generator": "tools/historical_growth.py",
            "brief_id": brief["id"],
            "map_id": brief["map_id"],
            "name": brief["name"],
            "seed": brief["seed"],
            "cause": deepcopy(brief["cause"]),
            "story_motifs": deepcopy(brief.get("story_motifs", [])),
            "map_size": deepcopy(self.constraints["map_size"]),
            "nodes": [],
            "geography": [],
            "routes": [],
            "districts": [],
            "surfaces": [],
            "ponds": [],
            "infrastructure": [],
            "plots": [],
            "buildings": [],
            "props": [],
            "forest_patches": [],
            "phases": [],
            "entry": {},
            "decisions": [],
        }
        self.node_lookup: dict[str, dict[str, Any]] = {}
        self.special_nodes: dict[str, str] = {}

    def _id(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return f"{prefix}-{self._counters[prefix]:02d}"

    def _point(self, x: float, z: float) -> list[int]:
        return [
            round(clamp(x, self.margin, self.width - self.margin - 1)),
            round(clamp(z, self.margin, self.depth - self.margin - 1)),
        ]

    def _central_point(self, spread: float = 0.14) -> list[int]:
        return self._point(
            self.width * (0.5 + self.rng.uniform(-spread, spread)),
            self.depth * (0.5 + self.rng.uniform(-spread, spread)),
        )

    def _edge_gate(self, edge: str) -> list[int]:
        along_x = round(self.rng.uniform(self.width * 0.18, self.width * 0.82))
        along_z = round(self.rng.uniform(self.depth * 0.18, self.depth * 0.82))
        if edge == "north":
            return [along_x, self.margin]
        if edge == "south":
            return [along_x, self.depth - self.margin - 1]
        if edge == "west":
            return [self.margin, along_z]
        if edge == "east":
            return [self.width - self.margin - 1, along_z]
        raise ValueError(f"Unknown edge {edge!r}")

    def _node(self, kind: str, point: list[int], phase: str, **properties: Any) -> str:
        node_id = self._id("node")
        node = {"id": node_id, "kind": kind, "point": point, "phase": phase, **properties}
        self.plan["nodes"].append(node)
        self.node_lookup[node_id] = node
        return node_id

    def _route(
        self,
        kind: str,
        points: list[list[int]],
        phase: str,
        material: str,
        width: int,
        status: str = "active",
        curvature: float | None = None,
    ) -> str:
        route_id = self._id("route")
        if curvature is None:
            curvature = round(self.rng.uniform(0.12, 0.42), 3)
        self.plan["routes"].append(
            {
                "id": route_id,
                "kind": kind,
                "phase": phase,
                "status": status,
                "material": material,
                "width": width,
                "curvature": curvature,
                "seed": int(self.brief["seed"]) * 100 + self._counters["route"],
                "points": points,
            }
        )
        return route_id

    def _geography(
        self, kind: str, points: list[list[int]], width: int, phase: str = "prehistory"
    ) -> str:
        geography_id = self._id("geography")
        self.plan["geography"].append(
            {
                "id": geography_id,
                "kind": kind,
                "phase": phase,
                "material": "water",
                "width": width,
                "curvature": round(self.rng.uniform(0.26, 0.48), 3),
                "seed": int(self.brief["seed"]) * 1000 + self._counters["geography"],
                "points": points,
            }
        )
        return geography_id

    def _district(
        self, kind: str, node_id: str, phase: str, radius: int, uses: list[str]
    ) -> str:
        district_id = self._id("district")
        self.plan["districts"].append(
            {
                "id": district_id,
                "kind": kind,
                "center_node": node_id,
                "phase": phase,
                "radius": radius,
                "uses": uses,
            }
        )
        return district_id

    def _surface(
        self, kind: str, center: list[int], size: tuple[int, int], phase: str, material: str
    ) -> str:
        surface_id = self._id("surface")
        width, depth = size
        x = round(clamp(center[0] - width / 2, self.margin, self.width - self.margin - width))
        z = round(clamp(center[1] - depth / 2, self.margin, self.depth - self.margin - depth))
        self.plan["surfaces"].append(
            {
                "id": surface_id,
                "kind": kind,
                "phase": phase,
                "material": material,
                "rect": [x, z, width, depth],
            }
        )
        return surface_id

    def _infrastructure(
        self, kind: str, binding: str, center: list[int], phase: str
    ) -> str:
        infrastructure_id = self._id("infrastructure")
        aw, ah, ad = self.asset_sizes[binding]
        x = round(clamp(center[0] - aw / 2, self.margin, self.width - self.margin - aw))
        z = round(clamp(center[1] - ad / 2, self.margin, self.depth - self.margin - ad))
        self.plan["infrastructure"].append(
            {
                "id": infrastructure_id,
                "kind": kind,
                "binding": binding,
                "phase": phase,
                "origin": [x, 1, z],
                "rect": [x, z, aw, ad],
                "asset_size": [aw, ah, ad],
            }
        )
        return infrastructure_id

    def _seed_river_crossing(self) -> None:
        phase = "founding"
        crossing = self._central_point(0.09)
        west = self._edge_gate("west")
        east = self._edge_gate("east")
        west[1] = round(clamp(crossing[1] + self.rng.randint(-12, 8), self.margin, self.depth - self.margin - 1))
        east[1] = round(clamp(crossing[1] + self.rng.randint(-8, 12), self.margin, self.depth - self.margin - 1))
        bend_w = self._point((west[0] + crossing[0]) / 2, (west[1] + crossing[1]) / 2 + self.rng.randint(-7, 7))
        bend_e = self._point((east[0] + crossing[0]) / 2, (east[1] + crossing[1]) / 2 + self.rng.randint(-7, 7))
        self._geography("river", [west, bend_w, crossing, bend_e, east], width=self.rng.choice([5, 6]))

        crossing_id = self._node("crossing", crossing, phase, cause="ford")
        self.special_nodes["origin"] = crossing_id
        north_gate = self._edge_gate("north")
        south_gate = self._edge_gate("south")
        north_gate_id = self._node("gate", north_gate, phase, edge="north")
        south_gate_id = self._node("gate", south_gate, phase, edge="south")
        self.special_nodes["entry_gate"] = south_gate_id
        bridge_half = max(5, self.asset_sizes[self.brief["cause"]["bridge_binding"]][2] // 2)
        north_bank = self._point(crossing[0], crossing[1] - bridge_half)
        south_bank = self._point(crossing[0], crossing[1] + bridge_half)
        north_bend = self._point((north_gate[0] + crossing[0]) / 2 + self.rng.randint(-8, 8), (north_gate[1] + crossing[1]) / 2)
        south_bend = self._point((south_gate[0] + crossing[0]) / 2 + self.rng.randint(-8, 8), (south_gate[1] + crossing[1]) / 2)
        primary_width = int(self.constraints["primary_road_width"])
        self._route("primary_approach", [north_gate, north_bend, north_bank], phase, "road", primary_width)
        self._route("primary_approach", [south_bank, south_bend, south_gate], phase, "road", primary_width)
        self._infrastructure("bridge", self.brief["cause"]["bridge_binding"], crossing, "bridge_market")

        side = self.rng.choice([-1, 1])
        market = self._point(crossing[0] + side * self.rng.randint(17, 24), crossing[1] + self.rng.randint(9, 16))
        civic = self._point(crossing[0] - side * self.rng.randint(15, 22), crossing[1] - self.rng.randint(8, 15))
        residential = self._point(crossing[0] - side * self.rng.randint(22, 31), crossing[1] + self.rng.randint(20, 30))
        market_id = self._node("market", market, "bridge_market")
        civic_id = self._node("civic", civic, "bank_consolidation")
        residential_id = self._node("residential", residential, "late_housing")
        self.special_nodes.update(market=market_id, civic=civic_id, residential=residential_id)
        secondary_width = int(self.constraints["secondary_road_width"])
        self._route("bridgehead_lane", [south_bank, market], "bridge_market", "dirt_track", secondary_width)
        self._route("north_bank_lane", [north_bank, civic], "bank_consolidation", "dirt_track", secondary_width)
        self._route("bank_expansion", [market, residential], "late_housing", "dirt_track", secondary_width)
        self._surface("market_widening", market, (18, 11), "bridge_market", "civic_stone")
        self._district("bridgehead", crossing_id, phase, 20, ["passage", "inn", "chapel"])
        self._district("market", market_id, "bridge_market", 18, ["commerce", "meeting"])
        self._district("civic", civic_id, "bank_consolidation", 17, ["administration", "ceremony"])
        self._district("bank_housing", residential_id, "late_housing", 26, ["residential", "gardens"])

    def _seed_road_confluence(self) -> None:
        phase = "roadside_origin"
        junction = self._central_point(0.11)
        junction_id = self._node("junction", junction, phase)
        self.special_nodes["origin"] = junction_id
        west = self._edge_gate("west")
        east = self._edge_gate("east")
        third_edge = self.rng.choice(["north", "south"])
        third = self._edge_gate(third_edge)
        west_id = self._node("gate", west, phase, edge="west")
        self._node("gate", east, phase, edge="east")
        self._node("gate", third, phase, edge=third_edge)
        self.special_nodes["entry_gate"] = west_id
        primary_width = int(self.constraints["primary_road_width"])
        secondary_width = int(self.constraints["secondary_road_width"])
        west_bend = self._point((west[0] + junction[0]) / 2, (west[1] + junction[1]) / 2 + self.rng.randint(-8, 8))
        east_bend = self._point((east[0] + junction[0]) / 2, (east[1] + junction[1]) / 2 + self.rng.randint(-8, 8))
        third_bend = self._point((third[0] + junction[0]) / 2 + self.rng.randint(-9, 9), (third[1] + junction[1]) / 2)
        self._route("regional_through_road", [west, west_bend, junction, east_bend, east], phase, "road", primary_width)
        self._route("third_road", [third, third_bend, junction], phase, "dirt_track", secondary_width)

        along = interpolate(junction, east, self.rng.uniform(0.52, 0.68))
        dx, dz = east[0] - junction[0], east[1] - junction[1]
        length = max(1.0, math.hypot(dx, dz))
        normal = (-dz / length, dx / length)
        freight_side = self.rng.choice([-1, 1])
        freight = self._point(along[0] + normal[0] * freight_side * 18, along[1] + normal[1] * freight_side * 18)
        market = self._point(junction[0] - normal[0] * freight_side * 10, junction[1] - normal[1] * freight_side * 10)
        civic = self._point(junction[0] - normal[0] * freight_side * 24, junction[1] - normal[1] * freight_side * 24)
        residential = self._point(junction[0] + normal[0] * freight_side * 28, junction[1] + normal[1] * freight_side * 28)
        freight_id = self._node("freight", freight, "freight_turnout")
        market_id = self._node("market", market, phase)
        civic_id = self._node("civic", civic, "civic_response")
        residential_id = self._node("residential", residential, "farm_edge_housing")
        self.special_nodes.update(freight=freight_id, market=market_id, civic=civic_id, residential=residential_id)
        self._route("freight_spur", [junction, freight], "freight_turnout", "dirt_track", secondary_width)
        self._route("civic_spur", [junction, civic], "civic_response", "dirt_track", secondary_width)
        self._route("farm_edge_lane", [junction, residential], "farm_edge_housing", "dirt_track", secondary_width)
        self._surface("freight_yard", freight, (32, 24), "freight_turnout", "civic_stone")
        self._surface("roadside_market", market, (17, 10), phase, "civic_stone")
        self._district("confluence", junction_id, phase, 18, ["inn", "commerce", "movement"])
        self._district("freight", freight_id, "freight_turnout", 21, ["storage", "loading"])
        self._district("civic", civic_id, "civic_response", 19, ["administration", "ceremony"])
        self._district("farm_edge", residential_id, "farm_edge_housing", 27, ["residential", "gardens"])

    def _seed_civic_accretion(self) -> None:
        phase = "formal_foundation"
        core = self._central_point(0.08)
        core_id = self._node("civic_core", core, phase)
        self.special_nodes.update(origin=core_id, civic=core_id)
        north = self._edge_gate("north")
        south = self._edge_gate("south")
        north[0] = round(clamp(core[0] + self.rng.randint(-4, 4), self.margin, self.width - self.margin - 1))
        south[0] = round(clamp(core[0] + self.rng.randint(-6, 6), self.margin, self.width - self.margin - 1))
        north_id = self._node("gate", north, phase, edge="north")
        self._node("gate", south, phase, edge="south")
        self.special_nodes["entry_gate"] = north_id
        primary_width = int(self.constraints["primary_road_width"])
        self._route("formal_axis", [north, core], phase, "road", primary_width, curvature=0.03)
        self._route("adapted_axis", [core, south], "plot_subdivision", "road", primary_width, curvature=0.19)
        self._surface("old_civic_court", core, (25, 21), phase, "civic_stone")
        basin = self._point(core[0] + self.rng.randint(-3, 3), core[1] + self.rng.randint(-2, 3))
        self.plan["ponds"].append(
            {
                "id": self._id("pond"),
                "kind": "court_basin",
                "phase": phase,
                "center": basin,
                "radius": 4,
                "irregularity": 0.07,
                "seed": int(self.brief["seed"]) * 100 + 91,
            }
        )
        side = self.rng.choice([-1, 1])
        market = self._point(core[0] + side * self.rng.randint(22, 29), core[1] + self.rng.randint(6, 15))
        residential = self._point(core[0] - side * self.rng.randint(23, 31), core[1] + self.rng.randint(20, 29))
        market_id = self._node("market", market, "market_shift")
        residential_id = self._node("residential", residential, "outer_accretion")
        self.special_nodes.update(market=market_id, residential=residential_id)
        market_edge = "east" if side > 0 else "west"
        market_gate = self._edge_gate(market_edge)
        residential_gate = self._edge_gate("west" if side > 0 else "east")
        secondary_width = int(self.constraints["secondary_road_width"])
        self._route("market_lane", [core, market, market_gate], "market_shift", "dirt_track", secondary_width)
        self._route("subdivision_lane", [core, residential, residential_gate], "plot_subdivision", "dirt_track", secondary_width)
        self._surface("shifted_market", market, (16, 9), "market_shift", "civic_stone")
        self._district("old_court", core_id, phase, 19, ["administration", "ceremony"])
        self._district("shifted_market", market_id, "market_shift", 18, ["commerce", "meeting"])
        self._district("subdivided_plots", residential_id, "plot_subdivision", 29, ["residential", "gardens"])

    def _seed_cause(self) -> None:
        cause_type = self.brief["cause"]["type"]
        if cause_type == "river_crossing":
            self._seed_river_crossing()
        elif cause_type == "road_confluence":
            self._seed_road_confluence()
        elif cause_type == "civic_accretion":
            self._seed_civic_accretion()
        else:
            raise ValueError(f"Unsupported cause type {cause_type!r}")
        self.plan["decisions"].append(
            {
                "decision": "derive causal geometry from seed and topology",
                "cause_type": cause_type,
                "input_coordinates": 0,
                "generated_nodes": len(self.plan["nodes"]),
                "generated_routes": len(self.plan["routes"]),
            }
        )

    def _active_route_segments(self, include_connectors: bool = False) -> list[tuple[dict[str, Any], list[int], list[int]]]:
        result = []
        for route in self.plan["routes"]:
            if route["status"] != "active":
                continue
            if route["kind"] == "connector" and not include_connectors:
                continue
            for start, end in zip(route["points"], route["points"][1:]):
                result.append((route, start, end))
        return result

    def _water_segments(self) -> list[tuple[dict[str, Any], list[int], list[int]]]:
        result = []
        for feature in self.plan["geography"]:
            if feature["kind"] != "river":
                continue
            for start, end in zip(feature["points"], feature["points"][1:]):
                result.append((feature, start, end))
        return result

    def _preferred_node(self, growth_rule: str) -> dict[str, Any]:
        mapping = {
            "cluster_at_cause": "origin",
            "market_frontage": "market",
            "freight_expansion": "freight",
            "civic_infill": "civic",
            "route_frontage": "residential",
            "edge_expansion": "residential",
        }
        key = mapping.get(growth_rule, "origin")
        node_id = self.special_nodes.get(key) or self.special_nodes["origin"]
        return self.node_lookup[node_id]

    def _district_for_point(self, point: tuple[float, float]) -> str:
        return min(
            self.plan["districts"],
            key=lambda district: distance(point, self.node_lookup[district["center_node"]]["point"]),
        )["id"]

    def _rect_crosses_water(self, rect: list[int]) -> bool:
        center = rect_center(rect)
        radius = math.hypot(rect[2] / 2, rect[3] / 2)
        for feature, start, end in self._water_segments():
            _, gap = nearest_on_segment(center, start, end)
            if gap < radius + feature["width"] / 2 + 1:
                return True
        return False

    def _candidate_valid(self, rect: list[int], plot: list[int]) -> bool:
        x, z, width, depth = rect
        if x < self.margin or z < self.margin or x + width >= self.width - self.margin or z + depth >= self.depth - self.margin:
            return False
        if self._rect_crosses_water(rect):
            return False
        for building in self.plan["buildings"]:
            if rects_overlap(rect, building["rect"], self.clearance):
                return False
        for existing_plot in self.plan["plots"]:
            if rects_overlap(plot, existing_plot["rect"], 0):
                return False
        for infrastructure in self.plan["infrastructure"]:
            if rects_overlap(rect, infrastructure["rect"], self.clearance):
                return False
        return True

    def _building_candidates(
        self, binding: str, growth_rule: str
    ) -> list[dict[str, Any]]:
        aw, ah, ad = self.asset_sizes[binding]
        preferred = self._preferred_node(growth_rule)
        origin = self.node_lookup[self.special_nodes["origin"]]
        desired_radius = {
            "cluster_at_cause": 14,
            "market_frontage": 16,
            "freight_expansion": 16,
            "civic_infill": 15,
            "route_frontage": 27,
            "edge_expansion": 38,
        }.get(growth_rule, 24)
        candidates = []
        samples = (0.16, 0.28, 0.40, 0.52, 0.64, 0.76, 0.88)
        for route, start, end in self._active_route_segments():
            dx, dz = end[0] - start[0], end[1] - start[1]
            segment_length = math.hypot(dx, dz)
            if segment_length < 5:
                continue
            normal = (-dz / segment_length, dx / segment_length)
            for amount in samples:
                target = interpolate(start, end, amount)
                for side in (-1, 1):
                    for setback_adjustment in (-2, 1, 4):
                        setback = max(aw, ad) / 2 + route["width"] / 2 + 3 + setback_adjustment
                        cx = target[0] + normal[0] * side * setback + self.rng.uniform(-2.5, 2.5)
                        cz = target[1] + normal[1] * side * setback + self.rng.uniform(-2.5, 2.5)
                        x = round(cx - aw / 2)
                        z = round(cz - ad / 2)
                        rect = [x, z, aw, ad]
                        entrance = [x + aw // 2, z + ad + 1]
                        plot_margin = self.rng.randint(2, 5)
                        plot = [x - plot_margin, z - plot_margin, aw + plot_margin * 2, ad + plot_margin * 2]
                        if not self._candidate_valid(rect, plot):
                            continue
                        target_block = self._point(*target)
                        preferred_gap = distance((cx, cz), preferred["point"])
                        origin_gap = distance((cx, cz), origin["point"])
                        radius_penalty = abs(origin_gap - desired_radius)
                        connector_length = distance(entrance, target_block)
                        score = (
                            preferred_gap * 0.78
                            + radius_penalty * 0.52
                            + connector_length * 0.32
                            + self.rng.random() * 3.0
                        )
                        candidates.append(
                            {
                                "score": score,
                                "rect": rect,
                                "plot": plot,
                                "entrance": entrance,
                                "connect_to": target_block,
                                "frontage_route": route["id"],
                                "asset_size": [aw, ah, ad],
                            }
                        )
        candidates.sort(key=lambda item: item["score"])
        return candidates

    def _fallback_candidate(self, binding: str, growth_rule: str) -> dict[str, Any] | None:
        aw, ah, ad = self.asset_sizes[binding]
        preferred = self._preferred_node(growth_rule)["point"]
        segments = self._active_route_segments()
        for _ in range(400):
            angle = self.rng.uniform(0, math.tau)
            radius = self.rng.uniform(16, 46)
            cx = preferred[0] + math.cos(angle) * radius
            cz = preferred[1] + math.sin(angle) * radius
            x, z = round(cx - aw / 2), round(cz - ad / 2)
            rect = [x, z, aw, ad]
            plot_margin = self.rng.randint(2, 4)
            plot = [x - plot_margin, z - plot_margin, aw + plot_margin * 2, ad + plot_margin * 2]
            if not self._candidate_valid(rect, plot):
                continue
            entrance = [x + aw // 2, z + ad + 1]
            route, target, _ = min(
                (
                    (route, nearest_on_segment(entrance, start, end)[0], nearest_on_segment(entrance, start, end)[1])
                    for route, start, end in segments
                ),
                key=lambda item: item[2],
            )
            return {
                "score": 999.0,
                "rect": rect,
                "plot": plot,
                "entrance": entrance,
                "connect_to": self._point(*target),
                "frontage_route": route["id"],
                "asset_size": [aw, ah, ad],
            }
        return None

    def _message(self, role: str, phase: str) -> str:
        cause = self.brief["cause"]["type"]
        introductions = {
            "river_crossing": "The old ford still decides where every lane bends.",
            "road_confluence": "Every road claims it reached Threeways first.",
            "civic_accretion": "The court was measured before the plots began to shift.",
        }
        role_lines = {
            "town hall": "We keep records of additions that were never meant to be permanent.",
            "chapel": "People gathered here before the settlement had a proper name.",
            "church": "The bells mark an older center than the market does.",
            "shop": "Trade follows the route people actually use, not the one on the plan.",
            "warehouse": "Goods need space, so the road always widens around us.",
            "crossing inn": "Travellers stop where geography makes them slow down.",
            "roadside inn": "The inn faces movement rather than ceremony.",
            "long house": "This building has served more purposes than its owners remember.",
            "apartment": "Our plot was divided from two older holdings.",
            "large house": "The lane arrived after the garden, then cut it in half.",
            "brick house": "The old boundary survives as a shortcut now.",
            "wooden house": "The newest homes always know the oldest back paths.",
        }
        return f"{introductions[cause]} {role_lines.get(role, f'This place belongs to the {phase.replace("_", " ")} phase.')}"

    def _place_building(self, item: dict[str, Any], phase: dict[str, Any]) -> str:
        binding = item["binding"]
        candidates = self._building_candidates(binding, phase["growth_rule"])
        candidate = candidates[0] if candidates else self._fallback_candidate(binding, phase["growth_rule"])
        if candidate is None:
            raise RuntimeError(f"Simulator could not place {item['role']} ({binding})")
        plot_id = self._id("plot")
        district_id = self._district_for_point(rect_center(candidate["rect"]))
        self.plan["plots"].append(
            {
                "id": plot_id,
                "phase": phase["id"],
                "district": district_id,
                "rect": candidate["plot"],
                "frontage_route": candidate["frontage_route"],
                "status": "occupied",
            }
        )
        building_id = self._id("building")
        building = {
            "id": building_id,
            "role": item["role"],
            "binding": binding,
            "phase": phase["id"],
            "district": district_id,
            "plot": plot_id,
            "rect": candidate["rect"],
            "origin": [candidate["rect"][0], 1, candidate["rect"][1]],
            "asset_size": candidate["asset_size"],
            "entrance": candidate["entrance"],
            "connect_to": candidate["connect_to"],
            "frontage_route": candidate["frontage_route"],
            "inhabitant": item["inhabitant"],
            "message": self._message(item["role"], phase["id"]),
            "rotation": int(self.constraints["building_rotation"]),
            "placement_score": round(candidate["score"], 3),
        }
        self.plan["buildings"].append(building)
        connector_id = self._route(
            "connector",
            [candidate["entrance"], candidate["connect_to"]],
            phase["id"],
            "dirt_track",
            int(self.constraints["tertiary_road_width"]),
            curvature=round(self.rng.uniform(0.05, 0.17), 3),
        )
        building["connector_route"] = connector_id
        return building_id

    def _history_mark(self, phase: dict[str, Any]) -> list[str]:
        created = []
        rule = phase["growth_rule"]
        origin = self.node_lookup[self.special_nodes["origin"]]["point"]
        if rule == "leave_obsolete_trace":
            used_edges = {node.get("edge") for node in self.plan["nodes"] if node["kind"] == "gate"}
            choices = [edge for edge in ("north", "south", "west", "east") if edge not in used_edges] or ["west", "south"]
            old_gate = self._edge_gate(self.rng.choice(choices))
            near_origin = self._point(
                origin[0] + self.rng.randint(-17, 17), origin[1] + self.rng.randint(-17, 17)
            )
            created.append(
                self._route(
                    "obsolete_route",
                    [old_gate, near_origin],
                    phase["id"],
                    "dirt_track",
                    1,
                    status="obsolete",
                    curvature=round(self.rng.uniform(0.34, 0.55), 3),
                )
            )
        elif rule == "leave_boundary_fragment":
            binding = self.brief["cause"]["surviving_boundary_binding"]
            side = self.rng.choice([-1, 1])
            center = self._point(origin[0] + side * 27, origin[1] - self.rng.randint(18, 25))
            created.append(self._infrastructure("boundary_fragment", binding, center, phase["id"]))
            trace_start = self._point(center[0] - side * 18, center[1] + self.rng.randint(7, 13))
            trace_end = self._point(center[0] + side * 22, center[1] + self.rng.randint(8, 15))
            created.append(
                self._route(
                    "obsolete_boundary",
                    [trace_start, trace_end],
                    phase["id"],
                    "dirt_track",
                    1,
                    status="obsolete",
                    curvature=0.07,
                )
            )
        return created

    def _run_phases(self) -> None:
        for phase in self.brief["phases"]:
            before = {
                "buildings": len(self.plan["buildings"]),
                "routes": len(self.plan["routes"]),
                "infrastructure": len(self.plan["infrastructure"]),
            }
            created_buildings = [self._place_building(item, phase) for item in phase.get("program", [])]
            created_marks = self._history_mark(phase)
            self.plan["phases"].append(
                {
                    "id": phase["id"],
                    "growth_rule": phase["growth_rule"],
                    "program": deepcopy(phase.get("program", [])),
                    "created_buildings": created_buildings,
                    "created_history_marks": created_marks,
                    "before": before,
                    "after": {
                        "buildings": len(self.plan["buildings"]),
                        "routes": len(self.plan["routes"]),
                        "infrastructure": len(self.plan["infrastructure"]),
                    },
                }
            )

    def _add_gardens(self) -> None:
        residential_tokens = ("house", "apartment")
        for building in self.plan["buildings"]:
            if not any(token in building["role"] for token in residential_tokens):
                continue
            x, z, width, depth = building["rect"]
            garden_width = max(6, min(11, width - 1))
            garden_depth = self.rng.randint(5, 8)
            side = self.rng.choice([-1, 1])
            gx = x + (width - garden_width) // 2
            gz = z - garden_depth - 2 if side < 0 else z + depth + 2
            rect = [gx, gz, garden_width, garden_depth]
            if gx < self.margin or gz < self.margin or gx + garden_width >= self.width - self.margin or gz + garden_depth >= self.depth - self.margin:
                continue
            if any(rects_overlap(rect, other["rect"], 1) for other in self.plan["buildings"]):
                continue
            self.plan["surfaces"].append(
                {
                    "id": self._id("surface"),
                    "kind": "kitchen_garden",
                    "phase": building["phase"],
                    "material": "dirt_track",
                    "rect": rect,
                    "building": building["id"],
                }
            )

    def _prop_free(self, point: list[int], radius: int) -> bool:
        x, z = point
        if x < self.margin + radius or z < self.margin + radius or x >= self.width - self.margin - radius or z >= self.depth - self.margin - radius:
            return False
        probe = [x - radius, z - radius, radius * 2 + 1, radius * 2 + 1]
        if any(rects_overlap(probe, building["rect"], 1) for building in self.plan["buildings"]):
            return False
        if any(distance(point, prop["point"]) < radius + prop.get("radius", 1) + 1 for prop in self.plan["props"]):
            return False
        if self._rect_crosses_water(probe):
            return False
        return True

    def _prop_near(self, kind: str, center: list[int], cluster: str, radius: int) -> str | None:
        prop_radius = {"lamp": 2, "flowerbed": 3, "bench": 2, "barrel": 1, "well": 3, "table": 2, "bush": 2, "rock": 2}.get(kind, 2)
        for _ in range(120):
            angle = self.rng.uniform(0, math.tau)
            gap = self.rng.uniform(max(3, radius * 0.25), radius)
            point = self._point(center[0] + math.cos(angle) * gap, center[1] + math.sin(angle) * gap)
            if not self._prop_free(point, prop_radius):
                continue
            prop_id = self._id("prop")
            self.plan["props"].append(
                {
                    "id": prop_id,
                    "kind": kind,
                    "cluster": cluster,
                    "point": point,
                    "rotation": self.rng.randrange(4),
                    "radius": prop_radius,
                }
            )
            return prop_id
        return None

    def _add_props(self) -> None:
        node_by_kind = {node["kind"]: node for node in self.plan["nodes"]}
        origin = self.node_lookup[self.special_nodes["origin"]]["point"]
        for route in self.plan["routes"]:
            if route["kind"] not in ("regional_through_road", "primary_approach", "formal_axis", "adapted_axis"):
                continue
            for start, end in zip(route["points"], route["points"][1:]):
                for amount in (0.28, 0.58, 0.82):
                    candidate = self._point(*interpolate(start, end, amount))
                    self._prop_near("lamp", candidate, "primary_route", 5)

        market = node_by_kind.get("market")
        if market:
            for kind in ("table", "table", "bench", "well", "lamp"):
                self._prop_near(kind, market["point"], "market", 10)
        freight = node_by_kind.get("freight")
        if freight:
            for kind in ("barrel", "barrel", "barrel", "barrel", "table", "lamp"):
                self._prop_near(kind, freight["point"], "freight", 13)
        civic = node_by_kind.get("civic") or node_by_kind.get("civic_core")
        if civic:
            for kind in ("bench", "bench", "flowerbed", "flowerbed", "well"):
                self._prop_near(kind, civic["point"], "civic", 13)
        for building in self.plan["buildings"]:
            if "house" in building["role"] or building["role"] == "apartment":
                center = self._point(*rect_center(building["rect"]))
                self._prop_near("flowerbed", center, f"domestic:{building['id']}", 12)
        if not self.plan["props"]:
            self._prop_near("well", origin, "origin", 12)

    def _add_forests(self) -> None:
        m = self.margin + 1
        candidates = [
            [m, m, 25, 13],
            [self.width - m - 25, m, 25, 13],
            [m, self.depth - m - 14, 27, 14],
            [self.width - m - 27, self.depth - m - 14, 27, 14],
            [m, round(self.depth * 0.38), 11, 28],
            [self.width - m - 11, round(self.depth * 0.38), 11, 28],
        ]
        self.rng.shuffle(candidates)
        gates = [node["point"] for node in self.plan["nodes"] if node["kind"] == "gate"]
        for rect in candidates:
            if len(self.plan["forest_patches"]) >= 3:
                break
            if any(rects_overlap(rect, building["rect"], 4) for building in self.plan["buildings"]):
                continue
            if any(rect[0] - 5 <= gate[0] <= rect[0] + rect[2] + 5 and rect[1] - 5 <= gate[1] <= rect[1] + rect[3] + 5 for gate in gates):
                continue
            self.plan["forest_patches"].append(
                {
                    "id": self._id("forest"),
                    "kind": "edge_grove",
                    "rect": rect,
                    "density": round(self.rng.uniform(0.48, 0.65), 3),
                    "clearing_rate": round(self.rng.uniform(0.24, 0.42), 3),
                    "spacing": self.rng.choice([5, 6]),
                    "max_count": self.rng.randint(12, 22),
                    "seed": int(self.brief["seed"]) * 10 + self._counters["forest"],
                }
            )

    def _set_entry(self) -> None:
        gate = self.node_lookup[self.special_nodes["entry_gate"]]
        segments = self._active_route_segments()
        adjacent = [item for item in segments if item[1] == gate["point"] or item[2] == gate["point"]]
        if not adjacent:
            adjacent = sorted(segments, key=lambda item: nearest_on_segment(gate["point"], item[1], item[2])[1])
        _, start, end = adjacent[0]
        toward = end if start == gate["point"] else start
        player = self._point(*interpolate(gate["point"], toward, 0.08))
        guide = self._point(*interpolate(gate["point"], toward, 0.22))
        self.plan["entry"] = {
            "gate_node": gate["id"],
            "player": player,
            "guide": guide,
            "guide_model": "guard",
            "message": f"Welcome to {self.brief['name']}. Follow the oldest active route toward the {self.brief['cause']['type'].replace('_', ' ')}.",
        }

    def _validate(self) -> None:
        expected = int(self.constraints["target_building_count"])
        if len(self.plan["buildings"]) != expected:
            raise RuntimeError(f"Expected {expected} buildings, generated {len(self.plan['buildings'])}")
        for index, building in enumerate(self.plan["buildings"]):
            x, z, width, depth = building["rect"]
            if x < 0 or z < 0 or x + width > self.width or z + depth > self.depth:
                raise RuntimeError(f"Building outside map: {building['id']}")
            for other in self.plan["buildings"][index + 1 :]:
                if rects_overlap(building["rect"], other["rect"], self.clearance):
                    raise RuntimeError(f"Building overlap: {building['id']} / {other['id']}")
            if not building.get("connector_route") or not building.get("plot") or not building.get("district"):
                raise RuntimeError(f"Incomplete semantic building instance: {building['id']}")
        if len(self.plan["phases"]) != len(self.brief["phases"]):
            raise RuntimeError("Not every brief phase was executed")
        if not self.plan["entry"]:
            raise RuntimeError("No entry route generated")

    def _metrics(self) -> dict[str, Any]:
        active = [route for route in self.plan["routes"] if route["status"] == "active" and route["kind"] != "connector"]
        bins = {
            angle_bin(start, end)
            for route in active
            for start, end in zip(route["points"], route["points"][1:])
        }
        plot_areas = [plot["rect"][2] * plot["rect"][3] for plot in self.plan["plots"]]
        origin = self.node_lookup[self.special_nodes["origin"]]["point"]
        phase_distance: dict[str, list[float]] = {}
        for building in self.plan["buildings"]:
            phase_distance.setdefault(building["phase"], []).append(distance(rect_center(building["rect"]), origin))
        return {
            "generated_spatial_records": sum(
                1
                for group in ("nodes", "routes", "surfaces", "ponds", "infrastructure", "plots", "buildings", "props", "forest_patches")
                for _ in self.plan[group]
            ),
            "input_coordinate_fields": 0,
            "nodes": len(self.plan["nodes"]),
            "active_routes": len(active),
            "obsolete_routes": sum(route["status"] == "obsolete" for route in self.plan["routes"]),
            "route_angle_bins_15deg": len(bins),
            "districts": len(self.plan["districts"]),
            "plots": len(self.plan["plots"]),
            "buildings": len(self.plan["buildings"]),
            "props": len(self.plan["props"]),
            "plot_area_cv": round(statistics.pstdev(plot_areas) / statistics.fmean(plot_areas), 4),
            "mean_building_distance_by_phase": {
                phase: round(statistics.fmean(values), 3) for phase, values in phase_distance.items()
            },
        }

    def run(self) -> dict[str, Any]:
        self._seed_cause()
        self._run_phases()
        self._add_gardens()
        self._add_props()
        self._add_forests()
        self._set_entry()
        self._validate()
        self.plan["metrics"] = self._metrics()
        canonical = json.dumps(self.plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self.plan["checksum"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return deepcopy(self.plan)


def generate_plan(
    brief: dict[str, Any],
    shared_constraints: dict[str, Any],
    asset_sizes: dict[str, list[int]],
) -> dict[str, Any]:
    return HistoricalGrowthSimulator(brief, shared_constraints, asset_sizes).run()
