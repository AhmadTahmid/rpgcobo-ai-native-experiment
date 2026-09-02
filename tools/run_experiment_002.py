#!/usr/bin/env python3
"""Experiment 002: autonomously adapt M982 into a detailed playable town.

The build stage discovers semantic resources, derives a spatial plan from a
surface grid, constructs the town through typed MCP tools, and leaves the draft
unsaved for visual review.  The finalize stage validates, saves, playtests, and
reload-verifies the reviewed draft.

No .bw file is parsed, copied, restored, or patched by this driver.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import sys
import time
from collections import Counter, deque
from pathlib import Path
from typing import Any, Callable

from ai_native_mcp import RPGCoboClient


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "work/agent-output"
RESULTS_PATH = OUTPUT_DIR / "experiment-002-results.json"
MAP_ID = "M982"

BRIEF = {
    "name": "Canalwatch",
    "intent": "A detailed, inhabited canal town adapted autonomously from RPG-Cobo's city template.",
    "constraints": [
        "Use only discovered project assets and authored map materials.",
        "Do not read or modify serialized .bw bytes.",
        "Do not hard-code building coordinates or resource IDs into the spatial planner.",
        "Preserve the template's canals, streets, lamps, terrain, and useful vegetation where possible.",
        "Use reversible typed mutations and leave saving until after inspection and validation.",
    ],
    "success_criteria": [
        "At least eight semantically distinct buildings placed without overlap.",
        "Each building connected to existing street infrastructure when a route can be found.",
        "Contextual inhabitants plus a guarded player entry.",
        "Authored props added through a general object-placement primitive.",
        "Zero validation errors before save and after reload.",
        "Successful test-play start, movement, interaction, screenshot, and stop.",
    ],
}

BUILDING_QUERIES = [
    "town hall",
    "apartment",
    "church",
    "shop",
    "warehouse",
    "brick house",
    "wooden house",
    "large house",
]

NPC_SPECS = {
    "town hall": ("mayor", "Welcome to Canalwatch. Every street here meets the water sooner or later."),
    "apartment": ("resident", "The canal breeze reaches every window in this quarter."),
    "church": ("priest", "The bells mark the tides as faithfully as they mark the hours."),
    "shop": ("merchant", "Fresh provisions, bridge rope, and dry boots—everything a traveler needs."),
    "warehouse": ("farmer", "Cargo comes off the eastern road and leaves by barge at dawn."),
    "brick house": ("old man", "I remember when the stone streets were only muddy tracks."),
    "wooden house": ("boy", "I race the lamp-lighter from the square to the canal!"),
    "large house": ("bard", "Canalwatch has nine bridges and at least twelve songs about them."),
}


def overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int], padding: int = 0) -> bool:
    return not (
        a[0] + a[2] + padding <= b[0]
        or b[0] + b[2] + padding <= a[0]
        or a[1] + a[3] + padding <= b[1]
        or b[1] + b[3] + padding <= a[1]
    )


def image_safe(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    content = value.get("content", [])
    if not any(isinstance(item, dict) and item.get("type") == "image" for item in content):
        return value
    return {
        "content": [
            {
                "type": item.get("type"),
                "mimeType": item.get("mimeType"),
                "encoded_bytes": len(item.get("data", "")),
            }
            for item in content
            if isinstance(item, dict)
        ]
    }


class Recorder:
    def __init__(self, results: dict[str, Any], stage: str, client: RPGCoboClient):
        self.results = results
        self.stage = stage
        self.client = client
        self.change_ids: list[str] = []

    def call(
        self,
        label: str,
        tool: str,
        arguments: dict[str, Any] | None = None,
        *,
        required: bool = True,
    ) -> Any:
        started = time.time()
        try:
            value = self.client.call(tool, arguments)
            elapsed = round(time.time() - started, 4)
            self.results["operations"].append(
                {
                    "stage": self.stage,
                    "label": label,
                    "tool": tool,
                    "arguments": arguments or {},
                    "elapsed_seconds": elapsed,
                    "result": image_safe(value),
                }
            )
            if isinstance(value, dict) and value.get("changeid"):
                self.change_ids.append(value["changeid"])
            return value
        except Exception as exc:
            self.results["failures"].append(
                {
                    "stage": self.stage,
                    "label": label,
                    "tool": tool,
                    "arguments": arguments or {},
                    "error": str(exc),
                    "required": required,
                }
            )
            if required:
                raise
            return None

    def rollback_all(self) -> None:
        for change_id in reversed(self.change_ids):
            try:
                self.call(
                    f"emergency rollback {change_id}",
                    "rpgcobo_change_rollback",
                    {"change_id": change_id},
                    required=False,
                )
            except Exception:
                pass


def get_rect(free_block: dict[str, Any]) -> tuple[int, int, int, int]:
    bounds = free_block.get("bounds")
    if bounds:
        return int(bounds[0]), int(bounds[2]), int(bounds[3]), int(bounds[5])
    pos = free_block["position"]
    return int(pos[0]), int(pos[2]), 1, 1


def derive_material_classes(summaries: list[dict[str, Any]]) -> tuple[set[int], set[int]]:
    build_ids: set[int] = set()
    water_ids: set[int] = set()
    for summary in summaries:
        for entry in summary["surface_blocks"] + summary["block_usage"]:
            block = entry["block"]
            if block.get("class") == "build":
                build_ids.add(block["id"])
            if block.get("class") == "water":
                water_ids.add(block["id"])
    return build_ids, water_ids


def plan_buildings(
    grid: dict[str, Any],
    assets: list[dict[str, Any]],
    existing_free_blocks: list[dict[str, Any]],
    build_ids: set[int],
    water_ids: set[int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    heights = grid["heights"]
    blocks = grid["surface_blocks"]
    traversable = grid["traversable"]
    map_width = grid["width"]
    map_depth = grid["depth"]
    existing_rects = [get_rect(item) for item in existing_free_blocks]
    candidates: dict[str, list[dict[str, Any]]] = {}
    diagnostics: dict[str, Any] = {}

    for asset in assets:
        aw, _, ad = asset["bounds"]["size"]
        offset = asset.get("properties", {}).get("plcoffs") or [0, 0, 0]
        possible: list[dict[str, Any]] = []
        rejected = Counter()
        for z in range(3, map_depth - ad - 3):
            for x in range(3, map_width - aw - 3):
                rect = (x, z, aw, ad)
                values = [heights[zz][xx] for zz in range(z, z + ad) for xx in range(x, x + aw)]
                if min(values) < 0:
                    rejected["missing_surface"] += 1
                    continue
                roughness = max(values) - min(values)
                if roughness > 1:
                    rejected["roughness_gt_1"] += 1
                    continue
                if any(blocks[zz][xx] in water_ids for zz in range(z, z + ad) for xx in range(x, x + aw)):
                    rejected["water"] += 1
                    continue
                if sum(traversable[zz][xx] for zz in range(z, z + ad) for xx in range(x, x + aw)) < aw * ad * 0.98:
                    rejected["low_traversability"] += 1
                    continue
                inside_build = sum(
                    blocks[zz][xx] in build_ids for zz in range(z, z + ad) for xx in range(x, x + aw)
                )
                if inside_build > aw * ad * 0.08:
                    rejected["existing_infrastructure"] += 1
                    continue
                object_count = sum(overlaps(rect, obstacle, 1) for obstacle in existing_rects)
                road_ring = sum(
                    blocks[zz][xx] in build_ids
                    for zz in range(max(0, z - 4), min(map_depth, z + ad + 4))
                    for xx in range(max(0, x - 4), min(map_width, x + aw + 4))
                    if not (x <= xx < x + aw and z <= zz < z + ad)
                )
                center_distance = ((x + aw / 2 - map_width / 2) ** 2 + (z + ad / 2 - map_depth / 2) ** 2) ** 0.5
                score = road_ring * 3 - inside_build * 10 - object_count * 80 - roughness * 80 - center_distance * 0.1
                surface_block = Counter(
                    blocks[zz][xx] for zz in range(z, z + ad) for xx in range(x, x + aw)
                ).most_common(1)[0][0]
                possible.append(
                    {
                        "asset_id": asset["id"],
                        "asset_name": asset["name"],
                        "query": asset["selection_query"],
                        "rect": list(rect),
                        "asset_origin": [x - int(offset[0]), max(values) + 1 - int(offset[1]), z - int(offset[2])],
                        "foundation_y": max(values),
                        "foundation_block": surface_block,
                        "roughness": roughness,
                        "road_ring_cells": road_ring,
                        "existing_object_conflicts": object_count,
                        "existing_build_cells": inside_build,
                        "score": round(score, 3),
                    }
                )
        possible.sort(key=lambda item: item["score"], reverse=True)
        candidates[asset["id"]] = possible[:300]
        diagnostics[asset["id"]] = {
            "accepted_before_cap": len(possible),
            "retained": len(candidates[asset["id"]]),
            "rejected": dict(rejected),
        }

    order = sorted(assets, key=lambda item: len(candidates[item["id"]]))
    chosen: list[dict[str, Any]] = []

    def select(index: int) -> bool:
        if index == len(order):
            return True
        asset = order[index]
        for candidate in candidates[asset["id"]]:
            rect = tuple(candidate["rect"])
            if any(overlaps(rect, tuple(other["rect"]), 2) for other in chosen):
                continue
            chosen.append(candidate)
            if select(index + 1):
                return True
            chosen.pop()
        return False

    if not select(0):
        raise RuntimeError("The deterministic packing search could not place every discovered town building")
    return chosen, {"candidate_diagnostics": diagnostics, "selection_order": [a["id"] for a in order]}


def nearest_external_start(rect: list[int], door: dict[str, Any] | None) -> tuple[int, int]:
    x, z, width, depth = rect
    if door:
        dx, _, dz, _ = door["position"]
        sides = [
            (abs(dx - x), (x - 2, max(z, min(z + depth - 1, int(dz))))),
            (abs(dx - (x + width - 1)), (x + width + 1, max(z, min(z + depth - 1, int(dz))))),
            (abs(dz - z), (max(x, min(x + width - 1, int(dx))), z - 2)),
            (abs(dz - (z + depth - 1)), (max(x, min(x + width - 1, int(dx))), z + depth + 1)),
        ]
        return min(sides, key=lambda item: item[0])[1]
    return x + width // 2, z + depth + 1


def route_to_road(
    start: tuple[int, int],
    grid: dict[str, Any],
    building_rects: list[tuple[int, int, int, int]],
    road_cells: set[tuple[int, int]],
    water_ids: set[int],
) -> list[tuple[int, int]]:
    width, depth = grid["width"], grid["depth"]
    blocks, traversable = grid["surface_blocks"], grid["traversable"]

    def valid(point: tuple[int, int]) -> bool:
        x, z = point
        if not (0 <= x < width and 0 <= z < depth):
            return False
        if blocks[z][x] in water_ids or not traversable[z][x]:
            return False
        return not any(overlaps((x, z, 1, 1), rect, 1) for rect in building_rects)

    if not valid(start):
        replacements = [
            (x, z)
            for radius in range(1, 8)
            for z in range(max(0, start[1] - radius), min(depth, start[1] + radius + 1))
            for x in range(max(0, start[0] - radius), min(width, start[0] + radius + 1))
            if valid((x, z))
        ]
        if not replacements:
            return []
        start = min(replacements, key=lambda point: abs(point[0] - start[0]) + abs(point[1] - start[1]))

    queue = deque([start])
    previous: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    target: tuple[int, int] | None = None
    while queue:
        point = queue.popleft()
        if point in road_cells:
            target = point
            break
        x, z = point
        for nxt in ((x + 1, z), (x - 1, z), (x, z + 1), (x, z - 1)):
            if nxt not in previous and valid(nxt):
                previous[nxt] = point
                queue.append(nxt)
    if target is None:
        return []
    path = []
    cursor: tuple[int, int] | None = target
    while cursor is not None:
        path.append(cursor)
        cursor = previous[cursor]
    return list(reversed(path))


def compress_route(path: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if len(path) <= 2:
        return path
    points = [path[0]]
    old_direction = (path[1][0] - path[0][0], path[1][1] - path[0][1])
    for index in range(2, len(path)):
        direction = (path[index][0] - path[index - 1][0], path[index][1] - path[index - 1][1])
        if direction != old_direction:
            points.append(path[index - 1])
            old_direction = direction
    points.append(path[-1])
    return points


def copy_capture(source: str, destination_name: str) -> str:
    destination = OUTPUT_DIR / destination_name
    shutil.copy2(ROOT / source, destination)
    return str(destination)


def new_results() -> dict[str, Any]:
    return {
        "experiment": "002",
        "map_id": MAP_ID,
        "brief": BRIEF,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "operations": [],
        "failures": [],
        "decisions": [],
        "plan": {},
        "artifacts": {},
    }


def write_results(results: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


def recorded_result(results: dict[str, Any], label: str) -> Any:
    for operation in results["operations"]:
        if operation["label"] == label:
            return operation["result"]
    raise KeyError(f"Recorded operation not found: {label}")


def build() -> int:
    results = new_results()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with RPGCoboClient(confirm_changes=True) as client:
        recorder = Recorder(results, "build", client)
        try:
            recorder.call("open city template", "rpgcobo_editor_open_data", {"id": MAP_ID})
            time.sleep(1)
            info = recorder.call("inspect baseline map", "rpgcobo_editor_map_get_info")
            if info["map_id"] != MAP_ID:
                raise RuntimeError(f"Expected {MAP_ID}, got {info['map_id']}")
            if info["counts"]["events"] or (info.get("player_start") and info["player_start"].get("mapid") == MAP_ID):
                raise RuntimeError("Experiment 002 build requires the uninhabited M982 baseline; refusing to duplicate a town")

            before_capture = recorder.call("capture baseline", "rpgcobo_editor_map_capture_view")
            results["artifacts"]["before"] = copy_capture(before_capture["path"], "M982-town-before.png")

            grid = recorder.call(
                "inspect planning surface",
                "rpgcobo_editor_map_get_surface_grid",
                {"x": 0, "z": 0, "width": 128, "depth": 128, "y_min": 0, "y_max": 15},
            )
            summaries = [
                recorder.call(
                    f"inspect quadrant {x},{z}",
                    "rpgcobo_editor_map_get_region_summary",
                    {"x": x, "z": z, "width": 64, "depth": 64},
                )
                for x, z in ((0, 0), (64, 0), (0, 64), (64, 64))
            ]
            baseline_objects = recorder.call(
                "inventory existing map objects",
                "rpgcobo_editor_map_list_assets",
                {"x": 0, "y": 0, "z": 0, "width": 128, "height": 64, "depth": 128, "limit": 500},
            )["free_blocks"]
            baseline_uids = {item["uid"] for item in baseline_objects}
            build_ids, water_ids = derive_material_classes(summaries)

            assets: list[dict[str, Any]] = []
            used_assets: set[str] = set()
            for query in BUILDING_QUERIES:
                matches = recorder.call(
                    f"discover {query} asset",
                    "rpgcobo_project_search_assets",
                    {"query": query, "types": "map_asset", "limit": 20},
                )["assets"]
                selected = next((item for item in matches if item["id"] not in used_assets), None)
                if not selected:
                    raise RuntimeError(f"No unused map asset discovered for semantic query {query!r}")
                detailed = recorder.call(
                    f"inspect selected {query}", "rpgcobo_project_get_asset_info", {"id": selected["id"]}
                )
                detailed["selection_query"] = query
                assets.append(detailed)
                used_assets.add(detailed["id"])

            placements, planner_diagnostics = plan_buildings(
                grid, assets, baseline_objects, build_ids, water_ids
            )
            results["plan"] = {
                "planner": {
                    "method": "bounded surface-grid scan, semantic asset queries, scored street adjacency, and deterministic non-overlap backtracking",
                    "coordinate_source": "derived from M982 surface and asset bounds; none supplied in the brief",
                    "build_surface_ids": sorted(build_ids),
                    "water_surface_ids": sorted(water_ids),
                    **planner_diagnostics,
                },
                "buildings": placements,
            }
            results["decisions"].append(
                {
                    "decision": "Use M982 rather than a blank map",
                    "reason": "The city template provides canals and authored street infrastructure, making the experiment test semantic adaptation and infill instead of merely procedural terrain painting.",
                }
            )
            results["decisions"].append(
                {
                    "decision": "Curate a semantic metadata overlay before planning",
                    "reason": "Localized asset names alone could not answer English brief terms such as shop, guard, or priest. Metadata entries are explicitly traceable to authored names and resource paths.",
                }
            )

            recorder.call(
                "rename adapted map",
                "rpgcobo_project_set_database_item",
                {"id": MAP_ID, "data": {"name": BRIEF["name"]}, "override": False},
                required=False,
            )

            removed_uids: set[int] = set()
            for placement in placements:
                rect = tuple(placement["rect"])
                conflicts = [
                    item for item in baseline_objects if item["uid"] not in removed_uids and overlaps(rect, get_rect(item), 0)
                ]
                for conflict in conflicts:
                    value = recorder.call(
                        f"clear object {conflict['uid']} from {placement['query']} plot",
                        "rpgcobo_editor_map_remove_free_block",
                        {"uid": conflict["uid"]},
                    )
                    if value:
                        removed_uids.add(conflict["uid"])
                if placement["roughness"]:
                    recorder.call(
                        f"level {placement['query']} foundation",
                        "rpgcobo_editor_map_fill_region",
                        {
                            "x": rect[0],
                            "y": placement["foundation_y"],
                            "z": rect[1],
                            "width": rect[2],
                            "height": 1,
                            "depth": rect[3],
                            "block": placement["foundation_block"],
                        },
                    )
                recorder.call(
                    f"place {placement['query']}",
                    "rpgcobo_editor_map_place_asset",
                    {
                        "asset_id": placement["asset_id"],
                        "x": placement["asset_origin"][0],
                        "y": placement["asset_origin"][1],
                        "z": placement["asset_origin"][2],
                        "rotation": 0,
                    },
                )

            after_buildings = recorder.call(
                "inspect baked building objects",
                "rpgcobo_editor_map_list_assets",
                {"x": 0, "y": 0, "z": 0, "width": 128, "height": 64, "depth": 128, "limit": 500},
            )["free_blocks"]
            new_objects = [item for item in after_buildings if item["uid"] not in baseline_uids]
            new_doors = [item for item in new_objects if item.get("class") == "door"]
            building_rects = [tuple(item["rect"]) for item in placements]
            road_cells = {
                (x, z)
                for z in range(grid["depth"])
                for x in range(grid["width"])
                if grid["surface_blocks"][z][x] in build_ids and grid["traversable"][z][x]
            }

            connectors: list[dict[str, Any]] = []
            for index, placement in enumerate(placements):
                rect = placement["rect"]
                doors = [item for item in new_doors if overlaps(tuple(rect), get_rect(item), 2)]
                door = doors[0] if doors else None
                start = nearest_external_start(rect, door)
                path = route_to_road(start, grid, building_rects, road_cells, water_ids)
                compressed = compress_route(path)
                connector = {
                    "asset_id": placement["asset_id"],
                    "query": placement["query"],
                    "door_uid": door["uid"] if door else None,
                    "door_position": door["position"] if door else None,
                    "route": [list(point) for point in path],
                    "segments": [list(point) for point in compressed],
                }
                connectors.append(connector)
                if len(compressed) < 2:
                    results["failures"].append(
                        {
                            "stage": "build",
                            "label": f"connect {placement['query']} to street",
                            "tool": "planner/breadth_first_search",
                            "arguments": {"start": start},
                            "error": "No non-trivial route to baseline street infrastructure",
                            "required": False,
                        }
                    )
                    continue
                target_x, target_z = path[-1]
                road_block = grid["surface_blocks"][target_z][target_x]
                for segment_index, (a, b) in enumerate(zip(compressed, compressed[1:])):
                    recorder.call(
                        f"connect {placement['query']} street segment {segment_index + 1}",
                        "rpgcobo_editor_map_create_path",
                        {
                            "start_x": a[0],
                            "start_z": a[1],
                            "end_x": b[0],
                            "end_z": b[1],
                            "width": 2,
                            "block": road_block,
                            "curvature": 0.0,
                            "seed": 2000 + index * 10 + segment_index,
                        },
                        required=False,
                    )
            results["plan"]["connectors"] = connectors

            lamp_search = recorder.call(
                "discover street lamps",
                "rpgcobo_project_search_map_materials",
                {"query": "streetlamp", "kind": "free_block", "limit": 20},
            )["materials"]
            lamps = [item for item in lamp_search if not item["hidden"]]
            if lamps:
                lamp = lamps[0]
                for index, connector in enumerate(connectors[:6]):
                    route = connector["route"]
                    if len(route) < 5:
                        continue
                    point = route[len(route) // 2]
                    recorder.call(
                        f"place connector lamp {index + 1}",
                        "rpgcobo_editor_map_place_free_block",
                        {
                            "fbtype": lamp["fbtype"],
                            "variation": lamp["variation"],
                            "x": point[0],
                            "y": -1,
                            "z": point[1],
                            "rotation": index % 4,
                            "allow_overlap": False,
                        },
                        required=False,
                    )

            flower_search = recorder.call(
                "discover flower beds",
                "rpgcobo_project_search_map_materials",
                {"query": "flowerbed", "kind": "free_block", "limit": 20},
            )["materials"]
            flowers = [item for item in flower_search if not item["hidden"]]
            for index, placement in enumerate(placements[:3]):
                if not flowers:
                    break
                x, z, width, depth = placement["rect"]
                candidates = [(x - 3, z + depth // 2), (x + width + 2, z + depth // 2)]
                point = next(
                    (
                        point
                        for point in candidates
                        if 1 <= point[0] < grid["width"] - 1
                        and 1 <= point[1] < grid["depth"] - 1
                        and grid["surface_blocks"][point[1]][point[0]] not in water_ids
                        and not any(overlaps((point[0], point[1], 1, 1), rect, 1) for rect in building_rects)
                    ),
                    None,
                )
                if point:
                    flower = flowers[index % len(flowers)]
                    recorder.call(
                        f"place civic flower bed {index + 1}",
                        "rpgcobo_editor_map_place_free_block",
                        {
                            "fbtype": flower["fbtype"],
                            "variation": flower["variation"],
                            "x": point[0],
                            "y": -1,
                            "z": point[1],
                            "rotation": index % 4,
                            "allow_overlap": False,
                        },
                        required=False,
                    )

            occupied_event_cells: set[tuple[int, int]] = set()
            for index, (placement, connector) in enumerate(zip(placements, connectors)):
                character_query, message = NPC_SPECS[placement["query"]]
                characters = recorder.call(
                    f"discover {character_query} character",
                    "rpgcobo_project_search_assets",
                    {"query": character_query, "types": "chara_vox", "limit": 20},
                )["assets"]
                if not characters:
                    raise RuntimeError(f"No character discovered for {character_query!r}")
                route = connector["route"]
                if route:
                    point = route[min(3, len(route) - 1)]
                else:
                    x, z, width, depth = placement["rect"]
                    point = [x + width // 2, z + depth + 2]
                while tuple(point) in occupied_event_cells:
                    point = [point[0] + 1, point[1]]
                occupied_event_cells.add(tuple(point))
                surface_y = grid["heights"][point[1]][point[0]]
                recorder.call(
                    f"create {character_query} inhabitant",
                    "rpgcobo_editor_map_create_event",
                    {
                        "role": "villager",
                        "x": point[0],
                        "y": surface_y + 1,
                        "z": point[1],
                        "rotation": index % 4,
                        "name": f"*canalwatch-{character_query.replace(' ', '-')}",
                        "model_resource_id": characters[0]["id"],
                        "message": message,
                        "color": index % 6,
                    },
                )

            obstacle_points = {(int(item["position"][0]), int(item["position"][2])) for item in after_buildings}
            entry_candidates = [
                point
                for point in road_cells
                if point not in obstacle_points and not any(overlaps((point[0], point[1], 1, 1), rect, 2) for rect in building_rects)
            ]
            entry = min(
                entry_candidates,
                key=lambda point: (
                    min(point[0], point[1], grid["width"] - 1 - point[0], grid["depth"] - 1 - point[1]),
                    abs(point[0] - grid["width"] // 2) + abs(point[1] - grid["depth"] // 2),
                ),
            )
            inward = (
                2 if entry[0] < grid["width"] // 2 else -2 if entry[0] > grid["width"] // 2 else 0,
                2 if entry[1] < grid["depth"] // 2 else -2 if entry[1] > grid["depth"] // 2 else 0,
            )
            guard_point = (entry[0] + inward[0], entry[1] + inward[1])
            if guard_point not in road_cells:
                guard_point = min(
                    (point for point in road_cells if point != entry),
                    key=lambda point: abs(point[0] - entry[0]) + abs(point[1] - entry[1]),
                )
            recorder.call(
                "set town entry player start",
                "rpgcobo_editor_map_set_player_start",
                {"x": entry[0], "y": grid["heights"][entry[1]][entry[0]] + 1, "z": entry[1], "rotation": 0},
            )
            guards = recorder.call(
                "discover guard character",
                "rpgcobo_project_search_assets",
                {"query": "guard", "types": "chara_vox", "limit": 20},
            )["assets"]
            recorder.call(
                "create entry guard",
                "rpgcobo_editor_map_create_event",
                {
                    "role": "villager",
                    "x": guard_point[0],
                    "y": grid["heights"][guard_point[1]][guard_point[0]] + 1,
                    "z": guard_point[1],
                    "rotation": 2,
                    "name": "*canalwatch-gate-guard",
                    "model_resource_id": guards[0]["id"],
                    "message": "Welcome to Canalwatch. The market and church both lie beyond the central square.",
                    "color": 1,
                },
            )
            results["plan"]["entry"] = {"player_start": list(entry), "guard": list(guard_point)}

            recorder.call("list town inhabitants", "rpgcobo_editor_map_list_events", {"offset": 0, "limit": 100})
            validation = recorder.call("validate unsaved town draft", "rpgcobo_map_validate", {"max_traversability_cells": 65536})
            if validation["errors"]:
                raise RuntimeError(f"Draft validation errors: {validation['errors']}")
            capture = recorder.call("capture town draft", "rpgcobo_editor_map_capture_view")
            results["artifacts"]["draft"] = copy_capture(capture["path"], "M982-town-draft.png")
            results["draft_ready_for_visual_review"] = True
        except Exception:
            recorder.rollback_all()
            results["draft_ready_for_visual_review"] = False
            write_results(results)
            raise
    write_results(results)
    print(json.dumps({"status": "draft-ready", "results": str(RESULTS_PATH), "artifacts": results["artifacts"]}, indent=2))
    return 0


def resume() -> int:
    """Recover the persisted first-pass town after the documented failed build."""
    if not RESULTS_PATH.exists():
        raise RuntimeError("No Experiment 002 results exist to resume")
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    baseline_grid = recorded_result(results, "inspect planning surface")
    placements = results["plan"]["buildings"]
    connectors = results["plan"]["connectors"]
    build_ids = set(results["plan"]["planner"]["build_surface_ids"])
    building_rects = [tuple(item["rect"]) for item in placements]

    with RPGCoboClient(confirm_changes=True) as client:
        recorder = Recorder(results, "recovery", client)
        try:
            info = recorder.call("inspect persisted partial town", "rpgcobo_editor_map_get_info")
            if info["map_id"] != MAP_ID or info["counts"]["events"] < 7:
                raise RuntimeError("Expected the persisted seven-inhabitant partial town")

            events = recorder.call(
                "inventory partial inhabitants", "rpgcobo_editor_map_list_events", {"offset": 0, "limit": 100}
            )["events"]
            for summary in events:
                event = recorder.call(
                    f"inspect partial event {summary['id']}",
                    "rpgcobo_editor_map_get_event",
                    {"event_id": summary["id"]},
                )["data"]
                if event.get("col", 0) not in range(6):
                    recorder.call(
                        f"repair invalid palette on event {summary['id']}",
                        "rpgcobo_editor_map_update_event",
                        {"event_id": summary["id"], "color": 0},
                    )

            recorder.call(
                "rename recovered town",
                "rpgcobo_project_set_database_item",
                {"id": MAP_ID, "data": {"name": BRIEF["name"]}, "override": False},
                required=False,
            )

            event_names = {item["name"] for item in events}
            if "*canalwatch-bard" not in event_names:
                placement = next(item for item in placements if item["query"] == "large house")
                connector = next(item for item in connectors if item["query"] == "large house")
                route = connector["route"]
                if route:
                    point = route[min(3, len(route) - 1)]
                else:
                    x, z, width, depth = placement["rect"]
                    point = [x + width // 2, z + depth + 2]
                bards = recorder.call(
                    "rediscover bard character",
                    "rpgcobo_project_search_assets",
                    {"query": "bard", "types": "chara_vox", "limit": 20},
                )["assets"]
                recorder.call(
                    "create recovered bard inhabitant",
                    "rpgcobo_editor_map_create_event",
                    {
                        "role": "villager",
                        "x": point[0],
                        "y": baseline_grid["heights"][point[1]][point[0]] + 1,
                        "z": point[1],
                        "rotation": 1,
                        "name": "*canalwatch-bard",
                        "model_resource_id": bards[0]["id"],
                        "message": NPC_SPECS["large house"][1],
                        "color": 1,
                    },
                )

            current_objects = recorder.call(
                "inventory recovered town objects",
                "rpgcobo_editor_map_list_assets",
                {"x": 0, "y": 0, "z": 0, "width": 128, "height": 64, "depth": 128, "limit": 500},
            )["free_blocks"]
            obstacle_points = {(int(item["position"][0]), int(item["position"][2])) for item in current_objects}
            road_cells = {
                (x, z)
                for z in range(baseline_grid["depth"])
                for x in range(baseline_grid["width"])
                if baseline_grid["surface_blocks"][z][x] in build_ids and baseline_grid["traversable"][z][x]
            }
            entry_candidates = [
                point
                for point in road_cells
                if point not in obstacle_points
                and not any(overlaps((point[0], point[1], 1, 1), rect, 2) for rect in building_rects)
            ]
            entry = min(
                entry_candidates,
                key=lambda point: (
                    min(
                        point[0],
                        point[1],
                        baseline_grid["width"] - 1 - point[0],
                        baseline_grid["depth"] - 1 - point[1],
                    ),
                    abs(point[0] - baseline_grid["width"] // 2)
                    + abs(point[1] - baseline_grid["depth"] // 2),
                ),
            )
            inward = (
                2 if entry[0] < baseline_grid["width"] // 2 else -2 if entry[0] > baseline_grid["width"] // 2 else 0,
                2 if entry[1] < baseline_grid["depth"] // 2 else -2 if entry[1] > baseline_grid["depth"] // 2 else 0,
            )
            guard_point = (entry[0] + inward[0], entry[1] + inward[1])
            if guard_point not in road_cells:
                guard_point = min(
                    (point for point in road_cells if point != entry),
                    key=lambda point: abs(point[0] - entry[0]) + abs(point[1] - entry[1]),
                )
            recorder.call(
                "set recovered town entry",
                "rpgcobo_editor_map_set_player_start",
                {
                    "x": entry[0],
                    "y": baseline_grid["heights"][entry[1]][entry[0]] + 1,
                    "z": entry[1],
                    "rotation": 0,
                },
            )
            guards = recorder.call(
                "rediscover guard character",
                "rpgcobo_project_search_assets",
                {"query": "guard", "types": "chara_vox", "limit": 20},
            )["assets"]
            recorder.call(
                "create recovered entry guard",
                "rpgcobo_editor_map_create_event",
                {
                    "role": "villager",
                    "x": guard_point[0],
                    "y": baseline_grid["heights"][guard_point[1]][guard_point[0]] + 1,
                    "z": guard_point[1],
                    "rotation": 2,
                    "name": "*canalwatch-gate-guard",
                    "model_resource_id": guards[0]["id"],
                    "message": "Welcome to Canalwatch. The market and church both lie beyond the central square.",
                    "color": 2,
                },
            )
            results["plan"]["entry"] = {"player_start": list(entry), "guard": list(guard_point)}
            results["recovery"] = {
                "reason": "The initial draft persisted after runtime_reload_tool, which is not a safe discard operation.",
                "actions": [
                    "Sanitized the invalid seventh-event palette index through the typed update-event command.",
                    "Added the remaining building inhabitant and guarded player entry.",
                    "Retained successful geometry and documented optional connector/prop failures.",
                ],
            }
            validation = recorder.call(
                "validate recovered town draft", "rpgcobo_map_validate", {"max_traversability_cells": 65536}
            )
            if validation["errors"]:
                raise RuntimeError(f"Recovered town validation errors: {validation['errors']}")
            capture = recorder.call("capture recovered town draft", "rpgcobo_editor_map_capture_view")
            results["artifacts"]["draft_recovered"] = copy_capture(
                capture["path"], "M982-town-draft-recovered.png"
            )
            results["draft_ready_for_visual_review"] = True
        except Exception:
            recorder.rollback_all()
            write_results(results)
            raise
    write_results(results)
    print(
        json.dumps(
            {"status": "recovered-draft-ready", "results": str(RESULTS_PATH), "artifacts": results["artifacts"]},
            indent=2,
        )
    )
    return 0


def finalize() -> int:
    if not RESULTS_PATH.exists():
        raise RuntimeError("Run the build stage before finalize")
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    with RPGCoboClient(confirm_changes=True) as client:
        recorder = Recorder(results, "finalize", client)
        info = recorder.call("inspect reviewed draft", "rpgcobo_editor_map_get_info")
        if info["map_id"] != MAP_ID or info["counts"]["events"] < 8:
            raise RuntimeError("The reviewed Experiment 002 draft is not open; refusing to finalize unrelated state")
        validation = recorder.call("validate reviewed town", "rpgcobo_map_validate", {"max_traversability_cells": 65536})
        if validation["errors"]:
            raise RuntimeError(f"Reviewed town has validation errors: {validation['errors']}")
        capture = recorder.call("capture reviewed town", "rpgcobo_editor_map_capture_view")
        results["artifacts"]["reviewed"] = copy_capture(capture["path"], "M982-town-reviewed.png")
        recorder.call("save reviewed town", "rpgcobo_runtime_save_all")

        debug = recorder.call(
            "start town playtest",
            "rpgcobo_debug_start",
            {"saveslot": -1, "debugitems": False, "debugskills": False, "debuglv": 0},
            required=False,
        )
        if debug is not None:
            state = None
            for attempt in range(20):
                time.sleep(0.5)
                state = recorder.call(
                    f"poll town player state {attempt + 1}", "rpgcobo_debug_get_player_state", required=False
                )
                if state and state.get("running"):
                    break
            if state and state.get("running"):
                entry = results["plan"]["entry"]["player_start"]
                guard = results["plan"]["entry"]["guard"]
                recorder.call(
                    "walk toward entry guard",
                    "rpgcobo_debug_player_move",
                    {"dx": (guard[0] - entry[0]) * 0.45, "dz": (guard[1] - entry[1]) * 0.45, "speed": 3.0},
                    required=False,
                )
                for attempt in range(10):
                    time.sleep(0.3)
                    moved = recorder.call(
                        f"poll guard approach {attempt + 1}", "rpgcobo_debug_get_player_state", required=False
                    )
                    if moved and not moved.get("moving"):
                        break
                recorder.call("interact with entry guard", "rpgcobo_debug_player_interact", required=False)
                recorder.call("capture town runtime", "rpgcobo_debug_screenshot", required=False)
            recorder.call("stop town playtest", "rpgcobo_debug_stop", required=False)

        recorder.call("reload saved tool state", "rpgcobo_runtime_reload_tool")

    time.sleep(5)
    with RPGCoboClient(confirm_changes=False) as client:
        recorder = Recorder(results, "reload-verification", client)
        recorder.call("reopen saved town", "rpgcobo_editor_open_data", {"id": MAP_ID})
        time.sleep(1)
        reloaded_info = recorder.call("inspect reloaded town", "rpgcobo_editor_map_get_info")
        reloaded_validation = recorder.call(
            "validate reloaded town", "rpgcobo_map_validate", {"max_traversability_cells": 65536}
        )
        if reloaded_info["counts"]["events"] < 8 or reloaded_validation["errors"]:
            raise RuntimeError("Reload verification failed")
        final_capture = recorder.call("capture reload-verified town", "rpgcobo_editor_map_capture_view")
        results["artifacts"]["final"] = copy_capture(final_capture["path"], "M982-town-final.png")

    results["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    results["completed"] = True
    write_results(results)
    print(
        json.dumps(
            {
                "status": "complete",
                "results": str(RESULTS_PATH),
                "operations": len(results["operations"]),
                "failures": len(results["failures"]),
                "artifacts": results["artifacts"],
            },
            indent=2,
        )
    )
    return 0


def polish() -> int:
    """Apply post-run semantic polish and persist a player-scale screenshot."""
    if not RESULTS_PATH.exists():
        raise RuntimeError("Run Experiment 002 before polish")
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    with RPGCoboClient(confirm_changes=True) as client:
        recorder = Recorder(results, "polish", client)
        info = recorder.call("inspect town before semantic polish", "rpgcobo_editor_map_get_info")
        if info["map_id"] != MAP_ID or info["counts"]["events"] < 9:
            raise RuntimeError("Completed Experiment 002 town is not open")
        recorder.call("set persistent town name", "rpgcobo_editor_map_set_name", {"name": BRIEF["name"]})
        recorder.call("save semantic polish", "rpgcobo_runtime_save_all")

        debug = recorder.call(
            "start runtime evidence session",
            "rpgcobo_debug_start",
            {"saveslot": -1, "debugitems": False, "debugskills": False, "debuglv": 0},
            required=False,
        )
        if debug is not None:
            state = None
            for attempt in range(20):
                time.sleep(0.5)
                state = recorder.call(
                    f"poll runtime evidence {attempt + 1}", "rpgcobo_debug_get_player_state", required=False
                )
                if state and state.get("running"):
                    break
            if state and state.get("running"):
                entry = results["plan"]["entry"]["player_start"]
                guard = results["plan"]["entry"]["guard"]
                recorder.call(
                    "approach guard for runtime evidence",
                    "rpgcobo_debug_player_move",
                    {"dx": (guard[0] - entry[0]) * 0.45, "dz": (guard[1] - entry[1]) * 0.45, "speed": 3.0},
                    required=False,
                )
                time.sleep(0.8)
                recorder.call("interact for runtime evidence", "rpgcobo_debug_player_interact", required=False)
                time.sleep(1.5)
                shot = recorder.call("capture persistent runtime evidence", "rpgcobo_debug_screenshot", required=False)
                if isinstance(shot, dict):
                    image_item = next(
                        (item for item in shot.get("content", []) if isinstance(item, dict) and item.get("type") == "image"),
                        None,
                    )
                    if image_item and image_item.get("data"):
                        suffix = ".png" if image_item.get("mimeType") == "image/png" else ".webp"
                        runtime_path = OUTPUT_DIR / f"M982-town-runtime{suffix}"
                        runtime_path.write_bytes(base64.b64decode(image_item["data"]))
                        results["artifacts"]["runtime"] = str(runtime_path)
            recorder.call("stop runtime evidence session", "rpgcobo_debug_stop", required=False)
        recorder.call("reload semantic polish", "rpgcobo_runtime_reload_tool")

    time.sleep(5)
    with RPGCoboClient(confirm_changes=False) as client:
        recorder = Recorder(results, "polish-verification", client)
        recorder.call("reopen polished town", "rpgcobo_editor_open_data", {"id": MAP_ID})
        time.sleep(1)
        info = recorder.call("verify persistent town name", "rpgcobo_editor_map_get_info")
        if info["name"] != BRIEF["name"]:
            raise RuntimeError(f"Town name did not persist: {info['name']!r}")
        validation = recorder.call(
            "validate polished town", "rpgcobo_map_validate", {"max_traversability_cells": 65536}
        )
        if validation["errors"]:
            raise RuntimeError(f"Polished town validation errors: {validation['errors']}")
    results["polished"] = True
    write_results(results)
    print(
        json.dumps(
            {
                "status": "polished",
                "name": BRIEF["name"],
                "results": str(RESULTS_PATH),
                "artifacts": results["artifacts"],
            },
            indent=2,
        )
    )
    return 0


def refine_semantics() -> int:
    """Correct a documented broad-query ranking error in the apartment resident."""
    if not RESULTS_PATH.exists():
        raise RuntimeError("Run Experiment 002 before semantic refinement")
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    with RPGCoboClient(confirm_changes=True) as client:
        recorder = Recorder(results, "semantic-refinement", client)
        residents = recorder.call(
            "discover specifically tagged resident",
            "rpgcobo_project_search_assets",
            {"query": "resident", "types": "chara_vox", "limit": 20},
        )["assets"]
        if not residents:
            raise RuntimeError("No specifically tagged resident character was discovered")
        events = recorder.call(
            "inspect inhabitants before semantic refinement",
            "rpgcobo_editor_map_list_events",
            {"offset": 0, "limit": 100},
        )["events"]
        apartment = next(
            (event for event in events if event["name"] in ("*canalwatch-woman", "*canalwatch-resident")),
            None,
        )
        if not apartment:
            raise RuntimeError("Apartment inhabitant was not found")
        recorder.call(
            "refine apartment inhabitant model",
            "rpgcobo_editor_map_update_event",
            {
                "event_id": apartment["id"],
                "name": "*canalwatch-resident",
                "model_resource_id": residents[0]["id"],
                "message": NPC_SPECS["apartment"][1],
                "color": 1,
            },
        )
        recorder.call("save semantic refinement", "rpgcobo_runtime_save_all")
        recorder.call("reload semantic refinement", "rpgcobo_runtime_reload_tool")
    time.sleep(5)
    with RPGCoboClient(confirm_changes=False) as client:
        recorder = Recorder(results, "semantic-refinement-verification", client)
        recorder.call("reopen semantically refined town", "rpgcobo_editor_open_data", {"id": MAP_ID})
        time.sleep(1)
        events = recorder.call(
            "verify refined apartment inhabitant", "rpgcobo_editor_map_list_events", {"offset": 0, "limit": 100}
        )["events"]
        apartment = next((event for event in events if event["name"] == "*canalwatch-resident"), None)
        if not apartment or apartment["model_resource_id"] != residents[0]["id"]:
            raise RuntimeError("Apartment inhabitant semantic refinement did not persist")
    results["semantic_refinement"] = {
        "before": "Broad query 'woman' selected CV001 by ID/path ordering.",
        "after": f"Specific curated tag 'resident' selected {residents[0]['id']} and the event survived reload.",
        "lesson": "Filtered semantic search still needs relevance ranking and explicit role compatibility.",
    }
    write_results(results)
    print(json.dumps({"status": "semantic-refinement-complete", "resident": residents[0]["id"]}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("build", "resume", "finalize", "polish", "refine"))
    args = parser.parse_args()
    if args.stage == "build":
        return build()
    if args.stage == "resume":
        return resume()
    if args.stage == "polish":
        return polish()
    if args.stage == "refine":
        return refine_semantics()
    return finalize()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Experiment 002 failed: {exc}", file=sys.stderr)
        raise
