#!/usr/bin/env python3
"""Experiment 004: concept-to-Town-DNA multi-variant autonomous generation.

The driver loads three normalized historical settlement grammars, grounds their
semantic vocabulary through RPG-Cobo's typed MCP tools, creates three genuinely
blank maps, constructs and validates each town, and records a complete trace.

Generated reference images are planning inputs only.  This program never reads,
writes, copies, or patches serialized .bw bytes directly.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import re
import shutil
import statistics
import time
from pathlib import Path
from typing import Any

from ai_native_mcp import RPGCoboClient


ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = ROOT / "docs/ai-native/experiment-004"
OUTPUT_DIR = ROOT / "work/agent-output"
RESULTS_PATH = OUTPUT_DIR / "experiment-004-results.json"
EVALUATION_PATH = SPEC_DIR / "agent-evaluation.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
            self.results["operations"].append(
                {
                    "stage": self.stage,
                    "label": label,
                    "tool": tool,
                    "arguments": arguments or {},
                    "elapsed_seconds": round(time.time() - started, 4),
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
            self.call(
                f"emergency rollback {change_id}",
                "rpgcobo_change_rollback",
                {"change_id": change_id},
                required=False,
            )


def new_results(grammar: dict[str, Any], bindings: dict[str, Any]) -> dict[str, Any]:
    prompts = load_json(SPEC_DIR / "concept-prompts.json")
    return {
        "experiment": "004",
        "objective": "Test an image-inspired but constraint-grounded Town DNA pipeline across three causal, template-free planning grammars.",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "claim_boundary": {
            "concepts": "Synthetic visual references used to propose composition and causal history.",
            "construction": "Only discovered RPG-Cobo assets, materials, and typed editor operations are used.",
            "from_blank": "Each variant begins as one uniform engine-generated ground layer with no objects or events.",
            "not_claimed": [
                "AI-authored source meshes, textures, characters, or engine",
                "pixel-perfect reproduction of generated references",
                "safe non-zero rotation of baked map assets",
            ],
        },
        "inputs": {
            "world_grammar": str(SPEC_DIR / "world_grammar.json"),
            "visual_style": str(SPEC_DIR / "visual_style.json"),
            "bindings": str(SPEC_DIR / "rpgcobo_bindings.json"),
            "concept_prompts": str(SPEC_DIR / "concept-prompts.json"),
            "concept_images": [str(SPEC_DIR / item["file"]) for item in prompts["concepts"]],
            "variant_ids": [item["id"] for item in grammar["variants"]],
            "binding_schema": bindings["schema"],
        },
        "operations": [],
        "failures": [],
        "decisions": [],
        "grounding": {},
        "variants": {},
        "artifacts": {},
    }


def write_results(results: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


def copy_capture(source: str, name: str) -> str:
    destination = OUTPUT_DIR / name
    shutil.copy2(ROOT / source, destination)
    return str(destination)


def map_ids_from_listing(value: Any) -> set[str]:
    texts: list[str] = []
    if isinstance(value, str):
        texts.append(value)
    elif isinstance(value, dict):
        for item in value.get("content", []):
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                texts.append(item["text"])
    elif isinstance(value, list):
        texts.extend(str(item) for item in value)
    return set(re.findall(r"\[(M\d{3})\]", "\n".join(texts)))


def select_asset(
    recorder: Recorder,
    label: str,
    binding: dict[str, Any],
    resource_type: str = "map_asset",
) -> dict[str, Any]:
    search = recorder.call(
        f"discover {label}",
        "rpgcobo_project_search_assets",
        {"query": binding["query"], "types": resource_type, "limit": 40},
    )
    matches = search["assets"]
    index = int(binding.get("result_index", 0))
    if index >= len(matches):
        raise RuntimeError(f"No result {index} for {label}: {binding['query']!r}")
    selected = matches[index]
    expected_id = binding.get("expected_id")
    if expected_id and selected["id"] != expected_id:
        raise RuntimeError(f"Grounding drift for {label}: expected {expected_id}, selected {selected['id']}")
    if resource_type == "map_asset":
        selected = recorder.call(
            f"inspect grounded {label}",
            "rpgcobo_project_get_asset_info",
            {"id": selected["id"]},
        )
    return selected


def select_material(recorder: Recorder, label: str, binding: dict[str, Any]) -> dict[str, Any]:
    search = recorder.call(
        f"discover {label} block material",
        "rpgcobo_project_search_map_materials",
        {"query": binding["query"], "kind": "block", "limit": 100},
    )
    visible = [item for item in search["materials"] if not item.get("hidden")]
    preferred = [item for item in visible if item.get("type") == binding.get("prefer_type")]
    selected = (preferred or visible)[0] if (preferred or visible) else None
    if not selected:
        raise RuntimeError(f"No visible block material for {label}")
    if binding.get("expected_id") is not None and selected["id"] != binding["expected_id"]:
        raise RuntimeError(
            f"Material grounding drift for {label}: expected {binding['expected_id']}, selected {selected['id']}"
        )
    return selected


def select_free_block(recorder: Recorder, label: str, binding: dict[str, Any]) -> dict[str, Any]:
    search = recorder.call(
        f"discover {label} free-block material",
        "rpgcobo_project_search_map_materials",
        {"query": binding["query"], "kind": "free_block", "limit": 100},
    )
    visible = [item for item in search["materials"] if not item.get("hidden")]
    index = int(binding.get("result_index", 0))
    if index >= len(visible):
        raise RuntimeError(f"No visible free-block result {index} for {label}")
    selected = visible[index]
    if binding.get("expected_fbtype") is not None and selected["fbtype"] != binding["expected_fbtype"]:
        raise RuntimeError(f"Free-block type drift for {label}")
    if binding.get("expected_variation") is not None and selected["variation"] != binding["expected_variation"]:
        raise RuntimeError(f"Free-block variation drift for {label}")
    return selected


def ground_vocabulary(
    recorder: Recorder, bindings: dict[str, Any], grammar: dict[str, Any]
) -> dict[str, Any]:
    grounded: dict[str, Any] = {"buildings": {}, "infrastructure": {}, "blocks": {}, "free_blocks": {}, "characters": {}}
    used_buildings = {item["binding"] for variant in grammar["variants"] for item in variant["buildings"]}
    used_infrastructure = {
        item["binding"] for variant in grammar["variants"] for item in variant.get("infrastructure", [])
    }
    used_props = {item["kind"] for variant in grammar["variants"] for item in variant.get("props", [])}
    used_characters = {
        item["inhabitant"] for variant in grammar["variants"] for item in variant["buildings"]
    } | {variant["entry"]["guide_model"] for variant in grammar["variants"]}

    for key in sorted(used_buildings):
        grounded["buildings"][key] = select_asset(recorder, f"building {key}", bindings["buildings"][key])
    for key in sorted(used_infrastructure):
        grounded["infrastructure"][key] = select_asset(
            recorder, f"infrastructure {key}", bindings["infrastructure"][key]
        )
    for key, binding in bindings["block_materials"].items():
        grounded["blocks"][key] = select_material(recorder, key, binding)
    for key in sorted(used_props):
        grounded["free_blocks"][key] = select_free_block(recorder, key, bindings["free_blocks"][key])

    tree_binding = bindings["free_blocks"]["trees"]
    tree_search = recorder.call(
        "discover bounded tree vocabulary",
        "rpgcobo_project_search_map_materials",
        {"query": tree_binding["query"], "kind": "free_block", "limit": 100},
    )
    allowed = set(tree_binding["allowed_variations"])
    grounded["trees"] = [
        item
        for item in tree_search["materials"]
        if not item.get("hidden")
        and item.get("fbtype") == tree_binding["fbtype"]
        and item.get("variation") in allowed
    ]
    if not grounded["trees"]:
        raise RuntimeError("No allowed tree variants were discovered")

    for query in sorted(used_characters):
        search = recorder.call(
            f"discover character {query}",
            "rpgcobo_project_search_assets",
            {"query": query, "types": "chara_vox", "limit": 20},
        )
        if not search["assets"]:
            raise RuntimeError(f"No character model discovered for {query!r}")
        grounded["characters"][query] = search["assets"][0]
    return grounded


def point(norm: list[float], width: int, depth: int) -> tuple[int, int]:
    return (
        max(0, min(width - 1, round(norm[0] * (width - 1)))),
        max(0, min(depth - 1, round(norm[1] * (depth - 1)))),
    )


def region(norm: list[float], width: int, depth: int) -> tuple[int, int, int, int]:
    x = max(0, min(width - 2, round(norm[0] * width)))
    z = max(0, min(depth - 2, round(norm[1] * depth)))
    w = max(1, round(norm[2] * width))
    d = max(1, round(norm[3] * depth))
    return x, z, min(w, width - x), min(d, depth - z)


def overlaps(a: tuple[int, int, int, int], b: tuple[int, int, int, int], clearance: int) -> bool:
    ax, az, aw, ad = a
    bx, bz, bw, bd = b
    return not (
        ax + aw + clearance <= bx
        or bx + bw + clearance <= ax
        or az + ad + clearance <= bz
        or bz + bd + clearance <= az
    )


def nearby_offsets(radius: int) -> list[tuple[int, int]]:
    offsets = [(0, 0)]
    for distance in range(2, radius + 1, 2):
        ring = [
            (dx, dz)
            for dx in range(-distance, distance + 1, 2)
            for dz in range(-distance, distance + 1, 2)
            if max(abs(dx), abs(dz)) == distance
        ]
        ring.sort(key=lambda value: (abs(value[0]) + abs(value[1]), value[1], value[0]))
        offsets.extend(ring)
    return offsets


def plan_assets(
    variant: dict[str, Any],
    grounded: dict[str, Any],
    width: int,
    depth: int,
    clearance: int,
    search_radius: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    occupied: list[tuple[int, int, int, int]] = []
    infrastructure: list[dict[str, Any]] = []
    for item in variant.get("infrastructure", []):
        asset = grounded["infrastructure"][item["binding"]]
        aw, ah, ad = asset["bounds"]["size"]
        cx, cz = point(item["anchor"], width, depth)
        x = max(3, min(width - aw - 3, cx - aw // 2))
        z = max(3, min(depth - ad - 3, cz - ad // 2))
        rect = (x, z, aw, ad)
        infrastructure.append({**item, "asset_id": asset["id"], "asset_size": [aw, ah, ad], "origin": [x, 1, z], "rect": list(rect)})
        occupied.append(rect)

    buildings: list[dict[str, Any]] = []
    for item in variant["buildings"]:
        asset = grounded["buildings"][item["binding"]]
        aw, ah, ad = asset["bounds"]["size"]
        cx, cz = point(item["anchor"], width, depth)
        base_x = max(4, min(width - aw - 4, cx - aw // 2))
        base_z = max(4, min(depth - ad - 4, cz - ad // 2))
        chosen: tuple[int, int, int, int] | None = None
        for dx, dz in nearby_offsets(search_radius):
            x = base_x + dx
            z = base_z + dz
            candidate = (x, z, aw, ad)
            if x < 4 or z < 4 or x + aw >= width - 4 or z + ad >= depth - 4:
                continue
            if not any(overlaps(candidate, other, clearance) for other in occupied):
                chosen = candidate
                break
        if chosen is None:
            raise RuntimeError(f"Could not pack {item['role']} near normalized anchor {item['anchor']}")
        occupied.append(chosen)
        x, z, _, _ = chosen
        buildings.append(
            {
                **item,
                "asset_id": asset["id"],
                "asset_name": asset.get("name"),
                "asset_size": [aw, ah, ad],
                "origin": [x, 1, z],
                "rect": list(chosen),
                "anchor_displacement": [x - base_x, z - base_z],
            }
        )
    return buildings, infrastructure


def baseline_ok(info: dict[str, Any], contract: dict[str, Any], map_id: str) -> bool:
    return (
        info["map_id"] == map_id
        and [info["size"]["width"], info["size"]["height"], info["size"]["depth"]] == contract["size"]
        and info["counts"]["blocks"] == contract["blank_block_count"]
        and info["counts"]["free_blocks"] == 0
        and info["counts"]["events"] == 0
    )


def create_paths(
    recorder: Recorder,
    variant: dict[str, Any],
    grounded: dict[str, Any],
    width: int,
    depth: int,
) -> list[dict[str, Any]]:
    compiled = []
    for item in variant.get("paths", []):
        start = point(item["start"], width, depth)
        end = point(item["end"], width, depth)
        args = {
            "start_x": start[0],
            "start_z": start[1],
            "end_x": end[0],
            "end_z": end[1],
            "width": item["width"],
            "block": grounded["blocks"][item["material"]]["id"],
            "curvature": item["curvature"],
            "seed": item["seed"],
        }
        recorder.call(f"create {item['label']}", "rpgcobo_editor_map_create_path", args)
        compiled.append({**item, "start_block": list(start), "end_block": list(end)})
    return compiled


def create_surfaces(
    recorder: Recorder,
    variant: dict[str, Any],
    grounded: dict[str, Any],
    width: int,
    depth: int,
) -> list[dict[str, Any]]:
    compiled = []
    for item in variant.get("surfaces", []):
        x, z, w, d = region(item["rect"], width, depth)
        recorder.call(
            f"fill {item['label']}",
            "rpgcobo_editor_map_fill_region",
            {
                "x": x,
                "y": 0,
                "z": z,
                "width": w,
                "height": 1,
                "depth": d,
                "block": grounded["blocks"][item["material"]]["id"],
            },
        )
        compiled.append({**item, "rect_block": [x, z, w, d]})
    return compiled


def create_ponds(
    recorder: Recorder,
    variant: dict[str, Any],
    grounded: dict[str, Any],
    width: int,
    depth: int,
) -> list[dict[str, Any]]:
    compiled = []
    for item in variant.get("ponds", []):
        center = point(item["center"], width, depth)
        recorder.call(
            f"create {item['label']}",
            "rpgcobo_editor_map_create_pond",
            {
                "center_x": center[0],
                "center_z": center[1],
                "radius": item["radius"],
                "water_block": grounded["blocks"]["water"]["id"],
                "water_y": 0,
                "irregularity": item["irregularity"],
                "seed": item["seed"],
            },
        )
        compiled.append({**item, "center_block": list(center)})
    return compiled


def place_asset_plan(recorder: Recorder, label: str, items: list[dict[str, Any]]) -> None:
    for item in items:
        recorder.call(
            f"place {label} {item['label'] if 'label' in item else item['role']}",
            "rpgcobo_editor_map_place_asset",
            {
                "asset_id": item["asset_id"],
                "x": item["origin"][0],
                "y": item["origin"][1],
                "z": item["origin"][2],
                "rotation": 0,
            },
        )


def connect_buildings(
    recorder: Recorder,
    buildings: list[dict[str, Any]],
    variant: dict[str, Any],
    grounded: dict[str, Any],
    width: int,
    depth: int,
    connector_width: int,
) -> list[dict[str, Any]]:
    connectors = []
    for index, building in enumerate(buildings):
        x, z, aw, ad = building["rect"]
        start = (x + aw // 2, min(depth - 2, z + ad + 1))
        end = point(building["connect_to"], width, depth)
        recorder.call(
            f"connect {building['role']}",
            "rpgcobo_editor_map_create_path",
            {
                "start_x": start[0],
                "start_z": start[1],
                "end_x": end[0],
                "end_z": end[1],
                "width": connector_width,
                "block": grounded["blocks"]["dirt_track"]["id"],
                "curvature": 0.08 + (index % 3) * 0.05,
                "seed": 4400 + index + sum(ord(char) for char in variant["id"]),
            },
        )
        connectors.append({"role": building["role"], "start": list(start), "end": list(end)})
    return connectors


def create_forests(
    recorder: Recorder,
    variant: dict[str, Any],
    grounded: dict[str, Any],
    width: int,
    depth: int,
) -> list[dict[str, Any]]:
    compiled = []
    tree_variations = [item["variation"] for item in grounded["trees"]]
    for item in variant.get("forest_patches", []):
        x, z, w, d = region(item["rect"], width, depth)
        recorder.call(
            f"grow {item['label']}",
            "rpgcobo_editor_map_create_forest_patch",
            {
                "x": x,
                "z": z,
                "width": w,
                "depth": d,
                "density": item["density"],
                "clearing_rate": item["clearing_rate"],
                "min_spacing": item["spacing"],
                "tree_fbtype": grounded["trees"][0]["fbtype"],
                "tree_variants": ",".join(str(value) for value in tree_variations),
                "max_count": item["max_count"],
                "seed": item["seed"],
            },
            required=False,
        )
        compiled.append({**item, "rect_block": [x, z, w, d]})
    return compiled


def place_props(
    recorder: Recorder,
    variant: dict[str, Any],
    grounded: dict[str, Any],
    width: int,
    depth: int,
) -> list[dict[str, Any]]:
    placed = []
    for group in variant.get("props", []):
        material = grounded["free_blocks"][group["kind"]]
        rotations = group.get("rotations", [])
        for index, normalized in enumerate(group["positions"]):
            x, z = point(normalized, width, depth)
            rotation = rotations[index % len(rotations)] if rotations else index % 4
            result = recorder.call(
                f"place {group['kind']} {index + 1}",
                "rpgcobo_editor_map_place_free_block",
                {
                    "fbtype": material["fbtype"],
                    "variation": material["variation"],
                    "x": x,
                    "y": -1,
                    "z": z,
                    "rotation": rotation,
                    "allow_overlap": False,
                },
                required=False,
            )
            placed.append({"kind": group["kind"], "position": [x, z], "rotation": rotation, "accepted": result is not None})
    return placed


def create_population(
    recorder: Recorder,
    variant: dict[str, Any],
    buildings: list[dict[str, Any]],
    connectors: list[dict[str, Any]],
    grounded: dict[str, Any],
    width: int,
    depth: int,
) -> dict[str, Any]:
    inhabitants = []
    for index, (building, connector) in enumerate(zip(buildings, connectors)):
        character = grounded["characters"][building["inhabitant"]]
        x, z = connector["end"]
        event = recorder.call(
            f"create {building['role']} inhabitant",
            "rpgcobo_editor_map_create_event",
            {
                "role": "villager",
                "x": x,
                "y": 2,
                "z": z,
                "rotation": index % 4,
                "name": f"*{variant['id']}-{building['inhabitant'].replace(' ', '-')}",
                "model_resource_id": character["id"],
                "message": building["message"],
                "color": index % 6,
            },
        )
        inhabitants.append({"role": building["role"], "model": character["id"], "position": [x, z], "event": event})

    player = point(variant["entry"]["player"], width, depth)
    guide = point(variant["entry"]["guide"], width, depth)
    recorder.call(
        "set causal-route player entry",
        "rpgcobo_editor_map_set_player_start",
        {"x": player[0], "y": 2, "z": player[1], "rotation": 0},
    )
    guard = grounded["characters"][variant["entry"]["guide_model"]]
    guide_event = recorder.call(
        "create entry guide",
        "rpgcobo_editor_map_create_event",
        {
            "role": "villager",
            "x": guide[0],
            "y": 2,
            "z": guide[1],
            "rotation": 2,
            "name": f"*{variant['id']}-entry-guide",
            "model_resource_id": guard["id"],
            "message": variant["entry"]["message"],
            "color": 1,
        },
    )
    return {
        "inhabitants": inhabitants,
        "entry": {"player": list(player), "guide": list(guide), "guide_event": guide_event},
    }


def build() -> int:
    grammar = load_json(SPEC_DIR / "world_grammar.json")
    bindings = load_json(SPEC_DIR / "rpgcobo_bindings.json")
    results = new_results(grammar, bindings)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with RPGCoboClient(confirm_changes=True) as client:
        grounding_recorder = Recorder(results, "grounding", client)
        listing = grounding_recorder.call(
            "list existing maps before template-free creation",
            "rpgcobo_project_list_database",
            {"type": "map", "limit": 1000},
        )
        existing_ids = map_ids_from_listing(listing)
        requested_ids = {item["map_id"] for item in grammar["variants"]}
        collisions = sorted(existing_ids & requested_ids)
        if collisions:
            raise RuntimeError(f"Refusing to overwrite existing Experiment 004 map IDs: {collisions}")
        grounded = ground_vocabulary(grounding_recorder, bindings, grammar)
        results["grounding"] = grounded
        results["decisions"].extend(bindings["reference_to_engine_translations"])
        write_results(results)

        contract = grammar["map_contract"]
        shared = grammar["shared_rules"]
        for variant in grammar["variants"]:
            variant_id = variant["id"]
            recorder = Recorder(results, f"build-{variant_id}", client)
            try:
                recorder.call(
                    f"create blank map {variant['map_id']}",
                    "rpgcobo_project_create_blank_map",
                    {
                        "map_id": variant["map_id"],
                        "name": f"Experiment 004 blank - {variant_id}",
                        "width": contract["size"][0],
                        "height": contract["size"][1],
                        "depth": contract["size"][2],
                        "ground_block": contract["ground_block"],
                        "ground_layers": contract["ground_layers"],
                        "group_id": -1,
                    },
                )
                recorder.call("open fresh blank map", "rpgcobo_editor_open_data", {"id": variant["map_id"]})
                time.sleep(0.5)
                info = recorder.call("verify exact blank baseline", "rpgcobo_editor_map_get_info")
                if not baseline_ok(info, contract, variant["map_id"]):
                    raise RuntimeError(f"Blank baseline contract failed for {variant_id}: {info}")
                validation = recorder.call(
                    "validate exact blank baseline",
                    "rpgcobo_map_validate",
                    {"max_traversability_cells": 65536},
                )
                if validation["errors"]:
                    raise RuntimeError(f"Blank baseline validation failed for {variant_id}: {validation['errors']}")
                before = recorder.call("capture blank baseline", "rpgcobo_editor_map_capture_view")
                before_path = copy_capture(before["path"], f"{variant['map_id']}-{variant_id}-before.png")

                width, _, depth = contract["size"]
                buildings, infrastructure = plan_assets(
                    variant,
                    grounded,
                    width,
                    depth,
                    int(shared["building_clearance"]),
                    int(shared["placement_search_radius"]),
                )
                recorder.call("name generated town", "rpgcobo_editor_map_set_name", {"name": variant["name"]})
                paths = create_paths(recorder, variant, grounded, width, depth)
                surfaces = create_surfaces(recorder, variant, grounded, width, depth)
                ponds = create_ponds(recorder, variant, grounded, width, depth)
                place_asset_plan(recorder, "infrastructure", infrastructure)
                place_asset_plan(recorder, "building", buildings)
                connectors = connect_buildings(
                    recorder,
                    buildings,
                    variant,
                    grounded,
                    width,
                    depth,
                    int(shared["connector_width"]),
                )
                forests = create_forests(recorder, variant, grounded, width, depth)
                props = place_props(recorder, variant, grounded, width, depth)
                population = create_population(recorder, variant, buildings, connectors, grounded, width, depth)

                recorder.call("inventory generated free blocks", "rpgcobo_editor_map_list_assets", {"limit": 500})
                recorder.call("inventory generated events", "rpgcobo_editor_map_list_events", {"limit": 100})
                final_validation = recorder.call(
                    "validate generated variant",
                    "rpgcobo_map_validate",
                    {"max_traversability_cells": 65536},
                )
                if final_validation["errors"]:
                    raise RuntimeError(f"Generated variant validation failed for {variant_id}: {final_validation['errors']}")
                draft = recorder.call("capture generated variant", "rpgcobo_editor_map_capture_view")
                draft_path = copy_capture(draft["path"], f"{variant['map_id']}-{variant_id}-draft.png")
                final_info = recorder.call("inspect generated variant", "rpgcobo_editor_map_get_info")
                recorder.call("save generated variant", "rpgcobo_runtime_save_all")

                results["variants"][variant_id] = {
                    "map_id": variant["map_id"],
                    "name": variant["name"],
                    "founding_cause": variant["founding_cause"],
                    "history_phases": variant["history_phases"],
                    "evaluation_intent": variant["evaluation_intent"],
                    "plan": {
                        "paths": paths,
                        "surfaces": surfaces,
                        "ponds": ponds,
                        "infrastructure": infrastructure,
                        "buildings": buildings,
                        "connectors": connectors,
                        "forests": forests,
                        "props": props,
                        **population,
                    },
                    "baseline": info,
                    "final_info": final_info,
                    "validation": final_validation,
                    "artifacts": {"before": before_path, "draft": draft_path},
                    "saved": True,
                }
                results["artifacts"][f"{variant_id}_draft"] = draft_path
                write_results(results)
            except Exception:
                recorder.rollback_all()
                write_results(results)
                raise

    print(
        json.dumps(
            {
                "status": "three-drafts-built",
                "variants": {key: value["artifacts"] for key, value in results["variants"].items()},
                "operations": len(results["operations"]),
                "failures": len(results["failures"]),
            },
            indent=2,
        )
    )
    return 0


def verify() -> int:
    if not RESULTS_PATH.exists():
        raise RuntimeError("Run the Experiment 004 build stage first")
    results = load_json(RESULTS_PATH)
    grammar = load_json(SPEC_DIR / "world_grammar.json")
    with RPGCoboClient(confirm_changes=True) as client:
        recorder = Recorder(results, "reload", client)
        recorder.call("reload saved multi-variant project", "rpgcobo_runtime_reload_tool")
    time.sleep(5)

    with RPGCoboClient(confirm_changes=False) as client:
        recorder = Recorder(results, "reload-verification", client)
        for variant in grammar["variants"]:
            variant_id = variant["id"]
            recorder.call(f"reopen {variant_id}", "rpgcobo_editor_open_data", {"id": variant["map_id"]})
            time.sleep(0.4)
            info = recorder.call(f"inspect reloaded {variant_id}", "rpgcobo_editor_map_get_info")
            validation = recorder.call(
                f"validate reloaded {variant_id}",
                "rpgcobo_map_validate",
                {"max_traversability_cells": 65536},
            )
            if info["name"] != variant["name"] or info["counts"]["events"] < 9 or validation["errors"]:
                raise RuntimeError(f"Reload verification failed for {variant_id}")
            capture = recorder.call(f"capture reloaded {variant_id}", "rpgcobo_editor_map_capture_view")
            path = copy_capture(capture["path"], f"{variant['map_id']}-{variant_id}-reloaded.png")
            results["variants"][variant_id]["reload_verification"] = {
                "info": info,
                "validation": validation,
                "artifact": path,
            }
            results["variants"][variant_id]["artifacts"]["reloaded"] = path
            results["artifacts"][f"{variant_id}_reloaded"] = path
            write_results(results)
    results["reload_verified"] = True
    write_results(results)
    print(json.dumps({"status": "reload-verified", "artifacts": results["artifacts"]}, indent=2))
    return 0


def mirror_difference(anchors: list[list[float]]) -> float:
    if not anchors:
        return 0.0
    distances = []
    for x, z in anchors:
        reflected = (1.0 - x, z)
        nearest = min(math.dist(reflected, other) for other in anchors)
        distances.append(nearest / math.sqrt(2))
    return statistics.fmean(distances)


def structural_metrics(variant: dict[str, Any], built: dict[str, Any]) -> dict[str, Any]:
    angles = []
    for item in variant.get("paths", []):
        dx = item["end"][0] - item["start"][0]
        dz = item["end"][1] - item["start"][1]
        angles.append((math.degrees(math.atan2(dz, dx)) + 180) % 180)
    angle_bins = len({round(angle / 15) for angle in angles})
    curvatures = [item["curvature"] for item in variant.get("paths", [])]
    connector_lengths = [math.dist(item["start"], item["end"]) for item in built["plan"]["connectors"]]
    connector_cv = (
        statistics.pstdev(connector_lengths) / statistics.fmean(connector_lengths)
        if len(connector_lengths) > 1 and statistics.fmean(connector_lengths)
        else 0.0
    )
    anchors = [item["anchor"] for item in variant["buildings"]]
    prop_acceptance = [item["accepted"] for item in built["plan"]["props"]]
    validation = built.get("reload_verification", {}).get("validation", built["validation"])
    return {
        "path_angle_bins_15deg": angle_bins,
        "mean_path_curvature": round(statistics.fmean(curvatures), 4),
        "building_mirror_difference": round(mirror_difference(anchors), 4),
        "connector_length_cv": round(connector_cv, 4),
        "surface_program_count": len(variant.get("surfaces", [])) + len(variant.get("ponds", [])),
        "functional_prop_categories": len(variant.get("props", [])),
        "history_phase_count": len(variant["history_phases"]),
        "prop_acceptance_rate": round(sum(prop_acceptance) / len(prop_acceptance), 4) if prop_acceptance else 1.0,
        "validation_errors": len(validation["errors"]),
        "validation_warnings": len(validation["warnings"]),
    }


def score() -> int:
    if not RESULTS_PATH.exists():
        raise RuntimeError("Run the Experiment 004 build stage first")
    results = load_json(RESULTS_PATH)
    grammar = load_json(SPEC_DIR / "world_grammar.json")
    for variant in grammar["variants"]:
        variant_id = variant["id"]
        built = results["variants"][variant_id]
        metrics = structural_metrics(variant, built)
        technical = 10.0 if metrics["validation_errors"] == 0 else 0.0
        technical *= metrics["prop_acceptance_rate"]
        diversity = min(
            10.0,
            metrics["path_angle_bins_15deg"] * 1.35
            + metrics["mean_path_curvature"] * 7.0
            + metrics["building_mirror_difference"] * 8.0
            + metrics["connector_length_cv"] * 4.0,
        )
        articulation = min(
            10.0,
            metrics["surface_program_count"] * 0.9
            + metrics["functional_prop_categories"] * 0.65
            + metrics["history_phase_count"] * 0.45,
        )
        results["variants"][variant_id]["automated_evaluation"] = {
            "metrics": metrics,
            "scores": {
                "technical_integrity": round(technical, 3),
                "structural_diversity": round(diversity, 3),
                "program_articulation": round(articulation, 3),
            },
            "selection_boundary": "These scores measure traceable structure, not visual quality. Agent visual review is a separate required input before selection.",
        }
    results["automated_scoring_complete"] = True
    write_results(results)
    print(
        json.dumps(
            {
                key: value["automated_evaluation"]
                for key, value in results["variants"].items()
            },
            indent=2,
        )
    )
    return 0


def apply_refinement_actions(
    recorder: Recorder,
    actions: dict[str, Any],
    grounded: dict[str, Any],
    width: int,
    depth: int,
) -> dict[str, Any]:
    applied: dict[str, Any] = {"removed_uids": [], "paths": [], "surfaces": [], "props": []}
    validation = recorder.call(
        "inspect selected map before refinement",
        "rpgcobo_map_validate",
        {"max_traversability_cells": 65536},
    )
    for warning in validation["warnings"]:
        if warning["code"] != "FREE_BLOCK_OUTSIDE_MAP":
            continue
        uid = warning["data"]["uid"]
        recorder.call(
            f"remove out-of-bounds free block {uid}",
            "rpgcobo_editor_map_remove_free_block",
            {"uid": uid},
        )
        applied["removed_uids"].append(uid)

    for item in actions.get("paths", []):
        start = point(item["start"], width, depth)
        end = point(item["end"], width, depth)
        recorder.call(
            f"refine path {item['label']}",
            "rpgcobo_editor_map_create_path",
            {
                "start_x": start[0],
                "start_z": start[1],
                "end_x": end[0],
                "end_z": end[1],
                "width": item["width"],
                "block": grounded["blocks"][item["material"]]["id"],
                "curvature": item["curvature"],
                "seed": item["seed"],
            },
        )
        applied["paths"].append({**item, "start_block": list(start), "end_block": list(end)})

    for item in actions.get("surfaces", []):
        x, z, w, d = region(item["rect"], width, depth)
        recorder.call(
            f"refine surface {item['label']}",
            "rpgcobo_editor_map_fill_region",
            {"x": x, "y": 0, "z": z, "width": w, "height": 1, "depth": d, "block": grounded["blocks"][item["material"]]["id"]},
        )
        applied["surfaces"].append({**item, "rect_block": [x, z, w, d]})

    for group in actions.get("props", []):
        material = grounded["free_blocks"][group["kind"]]
        rotations = group.get("rotations", [])
        for index, normalized in enumerate(group["positions"]):
            x, z = point(normalized, width, depth)
            rotation = rotations[index % len(rotations)] if rotations else index % 4
            result = recorder.call(
                f"refine prop {group['kind']} {index + 1}",
                "rpgcobo_editor_map_place_free_block",
                {"fbtype": material["fbtype"], "variation": material["variation"], "x": x, "y": -1, "z": z, "rotation": rotation, "allow_overlap": False},
                required=False,
            )
            applied["props"].append({"kind": group["kind"], "position": [x, z], "rotation": rotation, "accepted": result is not None})
    return applied


def refine() -> int:
    if not RESULTS_PATH.exists() or not EVALUATION_PATH.exists():
        raise RuntimeError("Run build/verify/score and create agent-evaluation.json before refinement")
    results = load_json(RESULTS_PATH)
    evaluation = load_json(EVALUATION_PATH)
    if results.get("selection", {}).get("refinement_applied"):
        raise RuntimeError("Selected refinement is already applied")
    selected = evaluation["selected_variant"]
    if selected not in results["variants"]:
        raise RuntimeError(f"Unknown selected variant {selected!r}")
    built = results["variants"][selected]

    with RPGCoboClient(confirm_changes=True) as client:
        recorder = Recorder(results, f"refine-{selected}", client)
        recorder.call("open autonomously selected variant", "rpgcobo_editor_open_data", {"id": built["map_id"]})
        time.sleep(0.5)
        info = recorder.call("inspect selected variant", "rpgcobo_editor_map_get_info")
        actions = evaluation.get("selected_refinement", {})
        applied = apply_refinement_actions(
            recorder,
            actions,
            results["grounding"],
            info["size"]["width"],
            info["size"]["depth"],
        )
        validation = recorder.call(
            "validate refined selected variant",
            "rpgcobo_map_validate",
            {"max_traversability_cells": 65536},
        )
        if validation["errors"] or any(item["code"] == "FREE_BLOCK_OUTSIDE_MAP" for item in validation["warnings"]):
            raise RuntimeError(f"Selected refinement failed validation: {validation}")
        capture = recorder.call("capture refined selected variant", "rpgcobo_editor_map_capture_view")
        path = copy_capture(capture["path"], f"{built['map_id']}-{selected}-refined.png")
        recorder.call("save refined selected variant", "rpgcobo_runtime_save_all")

    results["selection"] = {
        "selected_variant": selected,
        "evaluation_file": str(EVALUATION_PATH),
        "reason": evaluation["selection_reason"],
        "visual_scores": evaluation["visual_scores"],
        "refinement_applied": True,
        "refinement": applied,
        "validation": validation,
        "artifact": path,
    }
    results["variants"][selected]["artifacts"]["refined"] = path
    results["artifacts"]["selected_refined"] = path
    write_results(results)
    print(json.dumps({"status": "selected-and-refined", "selection": results["selection"]}, indent=2))
    return 0


def finalize() -> int:
    if not RESULTS_PATH.exists():
        raise RuntimeError("Run Experiment 004 through refinement first")
    results = load_json(RESULTS_PATH)
    selection = results.get("selection")
    if not selection or not selection.get("refinement_applied"):
        raise RuntimeError("No refined autonomous selection is recorded")
    selected = selection["selected_variant"]
    built = results["variants"][selected]
    if results.get("runtime_proof"):
        results.setdefault("runtime_attempts", []).append(results["runtime_proof"])
    results["completed"] = False
    results.pop("completed_at", None)
    write_results(results)

    with RPGCoboClient(confirm_changes=True) as client:
        recorder = Recorder(results, "selected-runtime-proof", client)
        recorder.call("open refined selected town", "rpgcobo_editor_open_data", {"id": built["map_id"]})
        time.sleep(0.5)
        validation = recorder.call(
            "validate selected town before runtime",
            "rpgcobo_map_validate",
            {"max_traversability_cells": 65536},
        )
        if validation["errors"]:
            raise RuntimeError(f"Selected town has runtime-blocking validation errors: {validation['errors']}")
        recorder.call("save selected town before runtime", "rpgcobo_runtime_save_all")
        recorder.call(
            "start selected town playtest",
            "rpgcobo_debug_start",
            {"saveslot": -1, "debugitems": False, "debugskills": False, "debuglv": 0},
        )
        state = None
        for attempt in range(20):
            time.sleep(0.5)
            state = recorder.call(
                f"poll selected runtime {attempt + 1}",
                "rpgcobo_debug_get_player_state",
                required=False,
            )
            if state and state.get("running"):
                break
        if not state or not state.get("running"):
            raise RuntimeError("Selected town did not reach a running runtime state")
        entry = built["plan"]["entry"]
        recorder.call(
            "walk toward selected entry guide",
            "rpgcobo_debug_player_move",
            {
                "dx": (entry["guide"][0] - entry["player"][0]) * 0.45,
                "dz": (entry["guide"][1] - entry["player"][1]) * 0.45,
                "speed": 3.0,
            },
        )
        target_state = None
        for attempt in range(30):
            time.sleep(0.3)
            moved = recorder.call(
                f"poll guide approach {attempt + 1}",
                "rpgcobo_debug_get_player_state",
                required=False,
            )
            if moved and moved.get("interaction_target_event_id") is not None:
                target_state = moved
                break
        if target_state is None:
            recorder.call("stop targetless selected playtest", "rpgcobo_debug_stop", required=False)
            write_results(results)
            raise RuntimeError("Selected entry guide never became an acquired interaction target")
        interaction = recorder.call("interact with selected entry guide", "rpgcobo_debug_player_interact")
        if not interaction.get("accepted"):
            time.sleep(0.8)
            interaction = recorder.call(
                "retry selected entry guide interaction after acquired target",
                "rpgcobo_debug_player_interact",
            )
        if not interaction.get("accepted"):
            recorder.call("stop rejected selected playtest", "rpgcobo_debug_stop", required=False)
            write_results(results)
            raise RuntimeError(f"Selected entry guide interaction was rejected: {interaction}")
        time.sleep(1.0)
        shot = recorder.call("capture selected runtime", "rpgcobo_debug_screenshot")
        image_item = next(
            (item for item in shot.get("content", []) if isinstance(item, dict) and item.get("type") == "image"),
            None,
        )
        runtime_path = None
        if image_item and image_item.get("data"):
            suffix = ".png" if image_item.get("mimeType") == "image/png" else ".webp"
            target = OUTPUT_DIR / f"{built['map_id']}-{selected}-runtime{suffix}"
            target.write_bytes(base64.b64decode(image_item["data"]))
            runtime_path = str(target)
        recorder.call("stop selected town playtest", "rpgcobo_debug_stop")
        recorder.call("save selected town after runtime", "rpgcobo_runtime_save_all")
        recorder.call("reload selected final state", "rpgcobo_runtime_reload_tool")

    time.sleep(5)
    with RPGCoboClient(confirm_changes=False) as client:
        recorder = Recorder(results, "selected-final-reload", client)
        recorder.call("reopen selected final town", "rpgcobo_editor_open_data", {"id": built["map_id"]})
        time.sleep(0.5)
        info = recorder.call("inspect selected final town", "rpgcobo_editor_map_get_info")
        final_validation = recorder.call(
            "validate selected final town",
            "rpgcobo_map_validate",
            {"max_traversability_cells": 65536},
        )
        if info["name"] != built["name"] or info["counts"]["events"] < 9 or final_validation["errors"]:
            raise RuntimeError("Selected final reload verification failed")
        final_capture = recorder.call("capture selected final town", "rpgcobo_editor_map_capture_view")
        final_path = copy_capture(final_capture["path"], f"{built['map_id']}-{selected}-final.png")

    results["runtime_proof"] = {
        "selected_variant": selected,
        "running_state_observed": True,
        "interaction": interaction,
        "runtime_artifact": runtime_path,
        "final_validation": final_validation,
        "final_info": info,
        "final_artifact": final_path,
    }
    results["artifacts"]["selected_runtime"] = runtime_path
    results["artifacts"]["selected_final"] = final_path
    results["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    results["completed"] = True
    write_results(results)
    print(
        json.dumps(
            {
                "status": "complete",
                "selected": selected,
                "operations": len(results["operations"]),
                "failures": len(results["failures"]),
                "artifacts": results["artifacts"],
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("build", "verify", "score", "refine", "finalize"))
    args = parser.parse_args()
    if args.stage == "build":
        return build()
    if args.stage == "verify":
        return verify()
    if args.stage == "score":
        return score()
    if args.stage == "refine":
        return refine()
    return finalize()


if __name__ == "__main__":
    raise SystemExit(main())
