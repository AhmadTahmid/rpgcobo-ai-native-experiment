#!/usr/bin/env python3
"""Experiment 005: compile causal historical-growth simulations into RPG-Cobo.

The compact briefs contain no spatial instructions.  ``simulate`` generates and
persists semantic plans; later stages ground those plans against real assets,
construct three blank maps, compare outcomes, refine one semantically, and prove
runtime interaction.  Serialized .bw bytes are never handled directly.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import shutil
import statistics
import time
from pathlib import Path
from typing import Any

from ai_native_mcp import RPGCoboClient
from historical_growth import generate_plan, rects_overlap
from run_experiment_004 import (
    Recorder,
    map_ids_from_listing,
    select_asset,
    select_free_block,
    select_material,
)


ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = ROOT / "docs/ai-native/experiment-005"
BRIEFS_PATH = SPEC_DIR / "briefs.json"
BINDINGS_PATH = ROOT / "docs/ai-native/experiment-004/rpgcobo_bindings.json"
OUTPUT_DIR = ROOT / "work/agent-output"
RESULTS_PATH = OUTPUT_DIR / "experiment-005-results.json"
EVALUATION_PATH = SPEC_DIR / "agent-evaluation.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def plan_path(brief_id: str) -> Path:
    return SPEC_DIR / f"generated-plan-{brief_id}.json"


def copy_capture(source: str, name: str) -> str:
    destination = OUTPUT_DIR / name
    shutil.copy2(ROOT / source, destination)
    return str(destination)


def capture_settled(recorder: Recorder, label: str, settle_seconds: float = 3.0) -> dict[str, Any]:
    """Drain the asynchronous overview renderer before copying its output."""
    recorder.call(label, "rpgcobo_editor_map_capture_view")
    time.sleep(settle_seconds)
    capture = recorder.call(f"{label} after renderer settle", "rpgcobo_editor_map_capture_view")
    time.sleep(settle_seconds)
    return capture


def expected_sizes(bindings: dict[str, Any]) -> dict[str, list[int]]:
    return {
        **{key: value["expected_size"] for key, value in bindings["buildings"].items()},
        **{key: value["expected_size"] for key, value in bindings["infrastructure"].items()},
    }


def simulate() -> int:
    briefs = load_json(BRIEFS_PATH)
    bindings = load_json(BINDINGS_PATH)
    sizes = expected_sizes(bindings)
    index = {
        "schema": "rpgcobo.ai-native.generated-town-plan-index.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "briefs": BRIEFS_PATH.relative_to(ROOT).as_posix(),
        "input_coordinate_fields": 0,
        "plans": [],
    }
    for brief in briefs["settlements"]:
        plan = generate_plan(brief, briefs["shared_constraints"], sizes)
        path = plan_path(brief["id"])
        write_json(path, plan)
        index["plans"].append(
            {
                "brief_id": brief["id"],
                "map_id": brief["map_id"],
                "name": brief["name"],
                "path": path.relative_to(ROOT).as_posix(),
                "checksum": plan["checksum"],
                "metrics": plan["metrics"],
            }
        )
    write_json(SPEC_DIR / "generated-plan-index.json", index)
    print(json.dumps(index, indent=2, ensure_ascii=False))
    return 0


def load_plans(briefs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    plans = {}
    for brief in briefs["settlements"]:
        path = plan_path(brief["id"])
        if not path.exists():
            raise RuntimeError("Run Experiment 005 simulate before constructing maps")
        plans[brief["id"]] = load_json(path)
    return plans


def new_results(briefs: dict[str, Any], plans: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "experiment": "005",
        "objective": "Test a deterministic historical-growth simulator whose causal briefs contain no authored spatial coordinates.",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "claim_boundary": {
            "input": "Cause type, phase rules, semantic building programs, non-spatial constraints, and seed.",
            "generated": "Nodes, geography, routes, districts, plots, building instances, entrances, connectors, surfaces, props, forests, and entry route.",
            "human_authored": "RPG-Cobo engine and source assets; simulator implementation and test briefs.",
            "forbidden_brief_fields": "Coordinates, anchors, points, path endpoints, positions, and rectangles.",
        },
        "inputs": {
            "briefs": str(BRIEFS_PATH),
            "bindings": str(BINDINGS_PATH),
            "plans": {key: str(plan_path(key)) for key in plans},
            "plan_checksums": {key: value["checksum"] for key, value in plans.items()},
            "input_coordinate_fields": 0,
        },
        "operations": [],
        "failures": [],
        "grounding": {},
        "variants": {},
        "artifacts": {},
        "decisions": [
            {
                "decision": "Persist the semantic plan separately from baked geometry",
                "reason": "RPG-Cobo loses MA provenance after placement; the generated plan retains phase, district, plot, entrance, frontage, and connector identity.",
            },
            {
                "decision": "Reuse Experiment 004's binding layer",
                "reason": "Experiment 005 isolates planning generality rather than changing the asset vocabulary simultaneously.",
            },
        ],
    }


def write_results(results: dict[str, Any]) -> None:
    write_json(RESULTS_PATH, results)


def ground_vocabulary(
    recorder: Recorder,
    briefs: dict[str, Any],
    plans: dict[str, dict[str, Any]],
    bindings: dict[str, Any],
) -> dict[str, Any]:
    grounded: dict[str, Any] = {
        "buildings": {},
        "infrastructure": {},
        "blocks": {},
        "free_blocks": {},
        "characters": {},
        "trees": [],
    }
    building_keys = {item["binding"] for plan in plans.values() for item in plan["buildings"]}
    infrastructure_keys = {item["binding"] for plan in plans.values() for item in plan["infrastructure"]}
    prop_keys = {item["kind"] for plan in plans.values() for item in plan["props"]}
    character_queries = {
        item["inhabitant"] for plan in plans.values() for item in plan["buildings"]
    } | {plan["entry"]["guide_model"] for plan in plans.values()}

    for key in sorted(building_keys):
        grounded["buildings"][key] = select_asset(
            recorder, f"building {key}", bindings["buildings"][key]
        )
    for key in sorted(infrastructure_keys):
        grounded["infrastructure"][key] = select_asset(
            recorder, f"infrastructure {key}", bindings["infrastructure"][key]
        )
    for key, binding in bindings["block_materials"].items():
        grounded["blocks"][key] = select_material(recorder, key, binding)
    for key in sorted(prop_keys):
        grounded["free_blocks"][key] = select_free_block(
            recorder, key, bindings["free_blocks"][key]
        )

    tree_binding = bindings["free_blocks"]["trees"]
    tree_search = recorder.call(
        "discover tree vocabulary for simulated edge growth",
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
        raise RuntimeError("No allowed tree variations were discovered")

    for query in sorted(character_queries):
        search = recorder.call(
            f"discover character {query}",
            "rpgcobo_project_search_assets",
            {"query": query, "types": "chara_vox", "limit": 20},
        )
        if not search["assets"]:
            raise RuntimeError(f"No character model discovered for {query!r}")
        grounded["characters"][query] = search["assets"][0]

    for plan in plans.values():
        for building in plan["buildings"]:
            actual = grounded["buildings"][building["binding"]]["bounds"]["size"]
            if actual != building["asset_size"]:
                raise RuntimeError(
                    f"Asset size drift invalidates generated plan {plan['brief_id']}: {building['binding']} {building['asset_size']} -> {actual}"
                )
        for infrastructure in plan["infrastructure"]:
            actual = grounded["infrastructure"][infrastructure["binding"]]["bounds"]["size"]
            if actual != infrastructure["asset_size"]:
                raise RuntimeError(f"Infrastructure size drift invalidates {plan['brief_id']}")
    return grounded


def compile_path(
    recorder: Recorder,
    feature: dict[str, Any],
    grounded: dict[str, Any],
    label_prefix: str,
) -> list[dict[str, Any]]:
    compiled = []
    for index, (start, end) in enumerate(zip(feature["points"], feature["points"][1:])):
        args = {
            "start_x": start[0],
            "start_z": start[1],
            "end_x": end[0],
            "end_z": end[1],
            "width": feature["width"],
            "block": grounded["blocks"][feature["material"]]["id"],
            "curvature": feature["curvature"],
            "seed": feature["seed"] + index,
        }
        recorder.call(
            f"compile {label_prefix} {feature['id']} segment {index + 1}",
            "rpgcobo_editor_map_create_path",
            args,
        )
        compiled.append({"feature": feature["id"], "segment": index, "start": start, "end": end})
    return compiled


def repair_bounds_warnings(recorder: Recorder, validation: dict[str, Any]) -> list[int]:
    removed = []
    for warning in validation["warnings"]:
        if warning["code"] != "FREE_BLOCK_OUTSIDE_MAP":
            continue
        uid = warning["data"]["uid"]
        recorder.call(
            f"remove generated-map out-of-bounds free block {uid}",
            "rpgcobo_editor_map_remove_free_block",
            {"uid": uid},
        )
        removed.append(uid)
    return removed


def build_variant(
    recorder: Recorder,
    brief: dict[str, Any],
    plan: dict[str, Any],
    shared: dict[str, Any],
    grounded: dict[str, Any],
) -> dict[str, Any]:
    map_id = brief["map_id"]
    recorder.call(
        f"create blank simulated map {map_id}",
        "rpgcobo_project_create_blank_map",
        {
            "map_id": map_id,
            "name": f"Experiment 005 blank - {brief['id']}",
            "width": shared["map_size"][0],
            "height": shared["map_size"][1],
            "depth": shared["map_size"][2],
            "ground_block": shared["ground_block"],
            "ground_layers": shared["ground_layers"],
            "group_id": -1,
        },
    )
    recorder.call("open exact simulated blank", "rpgcobo_editor_open_data", {"id": map_id})
    time.sleep(0.5)
    baseline = recorder.call("inspect exact simulated blank", "rpgcobo_editor_map_get_info")
    if (
        baseline["counts"]["blocks"] != 16384
        or baseline["counts"]["free_blocks"] != 0
        or baseline["counts"]["events"] != 0
    ):
        raise RuntimeError(f"Template-free baseline failed for {brief['id']}: {baseline}")
    baseline_validation = recorder.call(
        "validate exact simulated blank", "rpgcobo_map_validate", {"max_traversability_cells": 65536}
    )
    if baseline_validation["errors"]:
        raise RuntimeError(f"Blank validation errors for {brief['id']}")
    before = recorder.call("capture exact simulated blank", "rpgcobo_editor_map_capture_view")
    before_path = copy_capture(before["path"], f"{map_id}-{brief['id']}-before.png")
    recorder.call("name historically simulated town", "rpgcobo_editor_map_set_name", {"name": brief["name"]})

    compiled_segments = []
    for feature in plan["geography"]:
        compiled_segments.extend(compile_path(recorder, feature, grounded, "geography"))
    for route in plan["routes"]:
        if route["kind"] == "connector":
            continue
        compiled_segments.extend(compile_path(recorder, route, grounded, "route"))

    for surface in plan["surfaces"]:
        x, z, width, depth = surface["rect"]
        recorder.call(
            f"compile semantic surface {surface['id']} {surface['kind']}",
            "rpgcobo_editor_map_fill_region",
            {
                "x": x,
                "y": 0,
                "z": z,
                "width": width,
                "height": 1,
                "depth": depth,
                "block": grounded["blocks"][surface["material"]]["id"],
            },
        )
    for pond in plan["ponds"]:
        recorder.call(
            f"compile semantic pond {pond['id']}",
            "rpgcobo_editor_map_create_pond",
            {
                "center_x": pond["center"][0],
                "center_z": pond["center"][1],
                "radius": pond["radius"],
                "water_block": grounded["blocks"]["water"]["id"],
                "water_y": 0,
                "irregularity": pond["irregularity"],
                "seed": pond["seed"],
            },
        )
    for infrastructure in plan["infrastructure"]:
        asset = grounded["infrastructure"][infrastructure["binding"]]
        recorder.call(
            f"compile infrastructure {infrastructure['id']} {infrastructure['kind']}",
            "rpgcobo_editor_map_place_asset",
            {
                "asset_id": asset["id"],
                "x": infrastructure["origin"][0],
                "y": infrastructure["origin"][1],
                "z": infrastructure["origin"][2],
                "rotation": 0,
            },
        )
    for building in plan["buildings"]:
        asset = grounded["buildings"][building["binding"]]
        recorder.call(
            f"compile persistent building {building['id']} {building['role']}",
            "rpgcobo_editor_map_place_asset",
            {
                "asset_id": asset["id"],
                "x": building["origin"][0],
                "y": building["origin"][1],
                "z": building["origin"][2],
                "rotation": building["rotation"],
            },
        )
    for route in plan["routes"]:
        if route["kind"] != "connector":
            continue
        compiled_segments.extend(compile_path(recorder, route, grounded, "building connector"))

    tree_variants = ",".join(str(item["variation"]) for item in grounded["trees"])
    for forest in plan["forest_patches"]:
        x, z, width, depth = forest["rect"]
        recorder.call(
            f"compile forest zone {forest['id']}",
            "rpgcobo_editor_map_create_forest_patch",
            {
                "x": x,
                "z": z,
                "width": width,
                "depth": depth,
                "density": forest["density"],
                "clearing_rate": forest["clearing_rate"],
                "min_spacing": forest["spacing"],
                "tree_fbtype": grounded["trees"][0]["fbtype"],
                "tree_variants": tree_variants,
                "max_count": forest["max_count"],
                "seed": forest["seed"],
            },
            required=False,
        )

    prop_results = []
    for prop in plan["props"]:
        material = grounded["free_blocks"][prop["kind"]]
        result = recorder.call(
            f"compile prop {prop['id']} {prop['kind']} for {prop['cluster']}",
            "rpgcobo_editor_map_place_free_block",
            {
                "fbtype": material["fbtype"],
                "variation": material["variation"],
                "x": prop["point"][0],
                "y": -1,
                "z": prop["point"][1],
                "rotation": prop["rotation"],
                "allow_overlap": False,
            },
            required=False,
        )
        prop_results.append({"id": prop["id"], "accepted": result is not None})

    population = []
    for index, building in enumerate(plan["buildings"]):
        model = grounded["characters"][building["inhabitant"]]
        event = recorder.call(
            f"create phase-aware inhabitant for {building['id']}",
            "rpgcobo_editor_map_create_event",
            {
                "role": "villager",
                "x": building["connect_to"][0],
                "y": 2,
                "z": building["connect_to"][1],
                "rotation": index % 4,
                "name": f"*{brief['id']}-{building['id']}-{building['inhabitant'].replace(' ', '-')}",
                "model_resource_id": model["id"],
                "message": building["message"],
                "color": index % 6,
            },
        )
        population.append({"building": building["id"], "event": event, "model": model["id"]})
    entry = plan["entry"]
    recorder.call(
        "set generated historical entry",
        "rpgcobo_editor_map_set_player_start",
        {"x": entry["player"][0], "y": 2, "z": entry["player"][1], "rotation": 0},
    )
    guide_model = grounded["characters"][entry["guide_model"]]
    guide_event = recorder.call(
        "create generated historical entry guide",
        "rpgcobo_editor_map_create_event",
        {
            "role": "villager",
            "x": entry["guide"][0],
            "y": 2,
            "z": entry["guide"][1],
            "rotation": 2,
            "name": f"*{brief['id']}-entry-guide",
            "model_resource_id": guide_model["id"],
            "message": entry["message"],
            "color": 1,
        },
    )
    population.append({"building": None, "event": guide_event, "model": guide_model["id"]})

    first_validation = recorder.call(
        "validate compiled historical town", "rpgcobo_map_validate", {"max_traversability_cells": 65536}
    )
    if first_validation["errors"]:
        raise RuntimeError(f"Compiled historical town has errors: {first_validation['errors']}")
    removed_uids = repair_bounds_warnings(recorder, first_validation)
    final_validation = recorder.call(
        "validate autonomously repaired historical town",
        "rpgcobo_map_validate",
        {"max_traversability_cells": 65536},
    )
    if final_validation["errors"] or any(
        warning["code"] == "FREE_BLOCK_OUTSIDE_MAP" for warning in final_validation["warnings"]
    ):
        raise RuntimeError(f"Historical town repair failed: {final_validation}")
    info = recorder.call("inspect compiled historical town", "rpgcobo_editor_map_get_info")
    capture = recorder.call("capture compiled historical town", "rpgcobo_editor_map_capture_view")
    draft_path = copy_capture(capture["path"], f"{map_id}-{brief['id']}-draft.png")
    recorder.call("save compiled historical town", "rpgcobo_runtime_save_all")
    return {
        "map_id": map_id,
        "name": brief["name"],
        "plan_checksum": plan["checksum"],
        "plan_metrics": plan["metrics"],
        "semantic_counts": {
            "nodes": len(plan["nodes"]),
            "routes": len(plan["routes"]),
            "districts": len(plan["districts"]),
            "plots": len(plan["plots"]),
            "buildings": len(plan["buildings"]),
            "props_planned": len(plan["props"]),
            "phases": len(plan["phases"]),
        },
        "compiled_segments": compiled_segments,
        "prop_results": prop_results,
        "population": population,
        "autonomous_repairs": {"removed_out_of_bounds_uids": removed_uids},
        "baseline": baseline,
        "info": info,
        "validation": final_validation,
        "artifacts": {"before": before_path, "draft": draft_path},
    }


def build() -> int:
    briefs = load_json(BRIEFS_PATH)
    plans = load_plans(briefs)
    bindings = load_json(BINDINGS_PATH)
    fresh_results = new_results(briefs, plans)
    results = load_json(RESULTS_PATH) if RESULTS_PATH.exists() else fresh_results
    current_checksums = fresh_results["inputs"]["plan_checksums"]
    for variant_id, outcome in results.get("variants", {}).items():
        if outcome.get("plan_checksum") != current_checksums.get(variant_id):
            raise RuntimeError(
                f"Cannot resume {variant_id}: persisted result uses a different generated plan"
            )
    results["inputs"] = fresh_results["inputs"]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with RPGCoboClient(confirm_changes=True) as client:
        recorder = Recorder(results, "grounding", client)
        listing = recorder.call(
            "list maps before simulator compilation",
            "rpgcobo_project_list_database",
            {"type": "map", "limit": 1000},
        )
        existing = map_ids_from_listing(listing)
        requested = {brief["map_id"] for brief in briefs["settlements"]}
        resumable = {
            outcome["map_id"]
            for outcome in results.get("variants", {}).values()
            if outcome.get("map_id")
        }
        collisions = (existing & requested) - resumable
        if collisions:
            raise RuntimeError(f"Refusing to overwrite Experiment 005 map IDs: {sorted(collisions)}")
        grounded = results.get("grounding") or ground_vocabulary(recorder, briefs, plans, bindings)
        results["grounding"] = grounded
        write_results(results)
        for brief in briefs["settlements"]:
            if brief["id"] in results.get("variants", {}):
                continue
            variant_recorder = Recorder(results, f"build-{brief['id']}", client)
            try:
                outcome = build_variant(
                    variant_recorder,
                    brief,
                    plans[brief["id"]],
                    briefs["shared_constraints"],
                    grounded,
                )
                results["variants"][brief["id"]] = outcome
                results["artifacts"][f"{brief['id']}_draft"] = outcome["artifacts"]["draft"]
                write_results(results)
            except Exception:
                variant_recorder.rollback_all()
                write_results(results)
                raise
    print(
        json.dumps(
            {
                "status": "historical-towns-built",
                "operations": len(results["operations"]),
                "failures": len(results["failures"]),
                "variants": {key: value["artifacts"] for key, value in results["variants"].items()},
            },
            indent=2,
        )
    )
    return 0


def verify() -> int:
    if not RESULTS_PATH.exists():
        raise RuntimeError("Run Experiment 005 build first")
    briefs = load_json(BRIEFS_PATH)
    results = load_json(RESULTS_PATH)
    with RPGCoboClient(confirm_changes=True) as client:
        Recorder(results, "reload", client).call(
            "reload simulator-built project", "rpgcobo_runtime_reload_tool"
        )
    time.sleep(5)
    with RPGCoboClient(confirm_changes=False) as client:
        recorder = Recorder(results, "reload-verification", client)
        for brief in briefs["settlements"]:
            recorder.call(f"reopen {brief['id']}", "rpgcobo_editor_open_data", {"id": brief["map_id"]})
            time.sleep(0.4)
            info = recorder.call(f"inspect reloaded {brief['id']}", "rpgcobo_editor_map_get_info")
            validation = recorder.call(
                f"validate reloaded {brief['id']}",
                "rpgcobo_map_validate",
                {"max_traversability_cells": 65536},
            )
            if info["name"] != brief["name"] or info["counts"]["events"] < 9 or validation["errors"]:
                raise RuntimeError(f"Reload verification failed for {brief['id']}")
            capture = recorder.call(f"capture reloaded {brief['id']}", "rpgcobo_editor_map_capture_view")
            path = copy_capture(capture["path"], f"{brief['map_id']}-{brief['id']}-reloaded.png")
            results["variants"][brief["id"]]["reload_verification"] = {
                "info": info,
                "validation": validation,
                "artifact": path,
            }
            results["variants"][brief["id"]]["artifacts"]["reloaded"] = path
            results["artifacts"][f"{brief['id']}_reloaded"] = path
            write_results(results)
    results["reload_verified"] = True
    write_results(results)
    print(json.dumps({"status": "reload-verified", "artifacts": results["artifacts"]}, indent=2))
    return 0


def score() -> int:
    if not RESULTS_PATH.exists():
        raise RuntimeError("Run Experiment 005 build first")
    results = load_json(RESULTS_PATH)
    for variant_id, outcome in results["variants"].items():
        metrics = outcome["plan_metrics"]
        accepted = [item["accepted"] for item in outcome["prop_results"]]
        validation = outcome.get("reload_verification", {}).get("validation", outcome["validation"])
        phase_distances = list(metrics["mean_building_distance_by_phase"].values())
        historical_spread = (max(phase_distances) - min(phase_distances)) / max(1.0, max(phase_distances))
        technical = (10.0 if not validation["errors"] else 0.0) * (sum(accepted) / len(accepted) if accepted else 1.0)
        morphology = min(
            10.0,
            metrics["route_angle_bins_15deg"] * 1.1
            + metrics["plot_area_cv"] * 5.0
            + historical_spread * 4.0,
        )
        semantic = min(
            10.0,
            outcome["semantic_counts"]["districts"] * 1.3
            + outcome["semantic_counts"]["phases"] * 0.7,
        )
        outcome["automated_evaluation"] = {
            "scores": {
                "technical_integrity": round(technical, 3),
                "historical_morphology": round(morphology, 3),
                "semantic_persistence": round(semantic, 3),
            },
            "metrics": {
                **metrics,
                "historical_distance_spread": round(historical_spread, 4),
                "prop_acceptance_rate": round(sum(accepted) / len(accepted), 4) if accepted else 1.0,
            },
            "boundary": "Visual character and density require capture review; these scores measure structural evidence only.",
        }
    results["automated_scoring_complete"] = True
    write_results(results)
    print(
        json.dumps(
            {key: value["automated_evaluation"] for key, value in results["variants"].items()},
            indent=2,
        )
    )
    return 0


def generated_prop_positions(
    plan: dict[str, Any], node_kind: str, count: int, radius: int, seed: int
) -> list[list[int]]:
    import random

    rng = random.Random(seed)
    nodes = [node for node in plan["nodes"] if node["kind"] == node_kind]
    if not nodes:
        raise RuntimeError(f"Selected plan has no node kind {node_kind!r}")
    center = nodes[0]["point"]
    existing = [prop["point"] for prop in plan["props"]]
    positions = []
    for _ in range(500):
        if len(positions) >= count:
            break
        angle = rng.uniform(0, math.tau)
        gap = rng.uniform(max(4, radius * 0.35), radius)
        point = [round(center[0] + math.cos(angle) * gap), round(center[1] + math.sin(angle) * gap)]
        if not (5 <= point[0] < plan["map_size"][0] - 5 and 5 <= point[1] < plan["map_size"][2] - 5):
            continue
        probe = [point[0] - 2, point[1] - 2, 5, 5]
        if any(rects_overlap(probe, building["rect"], 2) for building in plan["buildings"]):
            continue
        if any(math.dist(point, other) < 5 for other in existing + positions):
            continue
        positions.append(point)
    return positions


def repair_generated_entry_obstructions(
    recorder: Recorder,
    results: dict[str, Any],
    selected: str,
    plan: dict[str, Any],
) -> list[dict[str, Any]]:
    """Move generated props that occupy the guide's immediate approach.

    The repair is derived from the generated entry vector and recorded placement
    UIDs; it does not introduce an authored map coordinate.
    """
    entry = plan["entry"]
    guide = entry["guide"]
    player = entry["player"]
    dx = guide[0] - player[0]
    dz = guide[1] - player[1]
    length = max(1.0, math.hypot(dx, dz))
    perpendicular = (-dz / length, dx / length)
    repairs = []
    operations = results.get("operations", [])
    for prop in plan["props"]:
        if math.dist(prop["point"], guide) > 2.5:
            continue
        placement = next(
            (
                operation
                for operation in operations
                if operation.get("stage") == f"build-{selected}"
                and operation.get("label", "").startswith(f"compile prop {prop['id']} ")
                and operation.get("result")
            ),
            None,
        )
        if not placement:
            continue
        uid = placement["result"]["details"].get("uid")
        if uid is None:
            continue
        current_y = placement["result"]["details"].get("free_block", {}).get("position", [0, 1, 0])[1]
        attempts = []
        accepted = None
        for side, distance in ((1, 6), (-1, 6), (1, 9), (-1, 9)):
            target = [
                round(guide[0] + perpendicular[0] * distance * side),
                round(guide[1] + perpendicular[1] * distance * side),
            ]
            attempts.append(target)
            moved = recorder.call(
                f"move generated {prop['id']} clear of entry approach",
                "rpgcobo_editor_map_move_free_block",
                {
                    "uid": uid,
                    "x": target[0],
                    "y": current_y,
                    "z": target[1],
                    "rotation": prop["rotation"],
                },
                required=False,
            )
            if moved is not None:
                accepted = target
                break
        repairs.append(
            {
                "prop_id": prop["id"],
                "uid": uid,
                "reason": "generated prop obstructed the generated entry-guide approach",
                "attempts": attempts,
                "accepted_target": accepted,
            }
        )
        if accepted is None:
            raise RuntimeError(f"Could not clear generated entry obstruction {prop['id']}")
    return repairs


def refine() -> int:
    if not RESULTS_PATH.exists() or not EVALUATION_PATH.exists():
        raise RuntimeError("Run score and create agent-evaluation.json before refinement")
    results = load_json(RESULTS_PATH)
    evaluation = load_json(EVALUATION_PATH)
    selected = evaluation["selected_variant"]
    if selected not in results["variants"]:
        raise RuntimeError(f"Unknown selected variant {selected!r}")
    if results.get("selection", {}).get("refinement_applied"):
        raise RuntimeError("Experiment 005 refinement is already applied")
    plan = load_json(plan_path(selected))
    outcome = results["variants"][selected]
    applied = {"prop_clusters": [], "removed_uids": []}
    with RPGCoboClient(confirm_changes=True) as client:
        recorder = Recorder(results, f"refine-{selected}", client)
        recorder.call("open historically selected town", "rpgcobo_editor_open_data", {"id": outcome["map_id"]})
        time.sleep(0.4)
        before = recorder.call(
            "validate selected historical town before refinement",
            "rpgcobo_map_validate",
            {"max_traversability_cells": 65536},
        )
        applied["removed_uids"] = repair_bounds_warnings(recorder, before)
        for cluster_index, cluster in enumerate(evaluation["selected_refinement"].get("prop_clusters", [])):
            positions = generated_prop_positions(
                plan,
                cluster["node_kind"],
                len(cluster["props"]),
                cluster.get("radius", 12),
                int(plan["seed"]) * 10 + cluster_index + 700,
            )
            records = []
            for index, (kind, point) in enumerate(zip(cluster["props"], positions)):
                material = results["grounding"]["free_blocks"][kind]
                result = recorder.call(
                    f"add semantic {cluster['node_kind']} {kind} {index + 1}",
                    "rpgcobo_editor_map_place_free_block",
                    {
                        "fbtype": material["fbtype"],
                        "variation": material["variation"],
                        "x": point[0],
                        "y": -1,
                        "z": point[1],
                        "rotation": index % 4,
                        "allow_overlap": False,
                    },
                    required=False,
                )
                records.append({"kind": kind, "point": point, "accepted": result is not None})
            applied["prop_clusters"].append({**cluster, "placements": records})
        validation = recorder.call(
            "validate semantically refined historical town",
            "rpgcobo_map_validate",
            {"max_traversability_cells": 65536},
        )
        if validation["errors"] or any(warning["code"] == "FREE_BLOCK_OUTSIDE_MAP" for warning in validation["warnings"]):
            raise RuntimeError(f"Experiment 005 selected refinement failed: {validation}")
        capture = capture_settled(recorder, "capture refined historical selection")
        path = copy_capture(capture["path"], f"{outcome['map_id']}-{selected}-refined.png")
        recorder.call("save refined historical selection", "rpgcobo_runtime_save_all")
    results["selection"] = {
        "selected_variant": selected,
        "reason": evaluation["selection_reason"],
        "visual_scores": evaluation["visual_scores"],
        "refinement_applied": True,
        "refinement": applied,
        "validation": validation,
        "artifact": path,
    }
    outcome["artifacts"]["refined"] = path
    results["artifacts"]["selected_refined"] = path
    write_results(results)
    print(json.dumps({"status": "selected-and-refined", "selection": results["selection"]}, indent=2))
    return 0


def finalize() -> int:
    if not RESULTS_PATH.exists():
        raise RuntimeError("Run Experiment 005 refinement first")
    results = load_json(RESULTS_PATH)
    selection = results.get("selection")
    if not selection or not selection.get("refinement_applied"):
        raise RuntimeError("No selected Experiment 005 refinement exists")
    selected = selection["selected_variant"]
    outcome = results["variants"][selected]
    plan = load_json(plan_path(selected))
    if results.get("runtime_proof"):
        results.setdefault("runtime_attempts", []).append(results["runtime_proof"])
    if (
        any(
            operation.get("stage") == "selected-runtime-proof"
            and operation.get("label") == "stop targetless simulated playtest"
            for operation in results.get("operations", [])
        )
        and not any(attempt.get("reason") == "no acquired interaction target" for attempt in results.get("runtime_attempts", []))
    ):
        results.setdefault("runtime_attempts", []).append(
            {
                "accepted": False,
                "reason": "no acquired interaction target",
                "diagnosis": "A generated lamp one block from the guide occupied the direct approach corridor.",
            }
        )
    results["completed"] = False
    results.pop("completed_at", None)
    write_results(results)

    with RPGCoboClient(confirm_changes=True) as client:
        recorder = Recorder(results, "selected-runtime-proof", client)
        recorder.call("open refined simulated town", "rpgcobo_editor_open_data", {"id": outcome["map_id"]})
        time.sleep(0.5)
        validation = recorder.call(
            "validate refined simulated town before runtime",
            "rpgcobo_map_validate",
            {"max_traversability_cells": 65536},
        )
        if validation["errors"]:
            raise RuntimeError("Selected Experiment 005 map is invalid before runtime")
        entry_repairs = repair_generated_entry_obstructions(
            recorder, results, selected, plan
        )
        results["entry_route_repairs"] = entry_repairs
        recorder.call("save selected simulated town before runtime", "rpgcobo_runtime_save_all")
        recorder.call(
            "start selected simulated town",
            "rpgcobo_debug_start",
            {"saveslot": -1, "debugitems": False, "debugskills": False, "debuglv": 0},
        )
        state = None
        for attempt in range(20):
            time.sleep(0.5)
            state = recorder.call(
                f"poll selected simulated runtime {attempt + 1}",
                "rpgcobo_debug_get_player_state",
                required=False,
            )
            if state and state.get("running"):
                break
        if not state or not state.get("running"):
            raise RuntimeError("Experiment 005 runtime did not reach running state")
        entry = plan["entry"]
        recorder.call(
            "walk generated entry route toward guide",
            "rpgcobo_debug_player_move",
            {
                "dx": (entry["guide"][0] - entry["player"][0]) * 0.45,
                "dz": (entry["guide"][1] - entry["player"][1]) * 0.45,
                "speed": 3.0,
            },
        )
        target_state = None
        for attempt in range(35):
            time.sleep(0.3)
            moved = recorder.call(
                f"poll generated guide acquisition {attempt + 1}",
                "rpgcobo_debug_get_player_state",
                required=False,
            )
            if moved and moved.get("interaction_target_event_id") is not None:
                target_state = moved
                break
        if target_state is None:
            recorder.call("stop targetless simulated playtest", "rpgcobo_debug_stop", required=False)
            write_results(results)
            raise RuntimeError("Generated entry guide never became an interaction target")
        interaction = recorder.call("interact with generated entry guide", "rpgcobo_debug_player_interact")
        if not interaction.get("accepted"):
            time.sleep(0.8)
            interaction = recorder.call("retry generated entry guide", "rpgcobo_debug_player_interact")
        if not interaction.get("accepted"):
            recorder.call("stop rejected simulated playtest", "rpgcobo_debug_stop", required=False)
            write_results(results)
            raise RuntimeError(f"Generated entry interaction rejected: {interaction}")
        time.sleep(1.0)
        shot = recorder.call("capture generated runtime dialogue", "rpgcobo_debug_screenshot")
        image_item = next(
            (item for item in shot.get("content", []) if isinstance(item, dict) and item.get("type") == "image"),
            None,
        )
        runtime_path = None
        if image_item and image_item.get("data"):
            suffix = ".png" if image_item.get("mimeType") == "image/png" else ".webp"
            target = OUTPUT_DIR / f"{outcome['map_id']}-{selected}-runtime{suffix}"
            target.write_bytes(base64.b64decode(image_item["data"]))
            runtime_path = str(target)
        recorder.call("stop selected simulated playtest", "rpgcobo_debug_stop")
        recorder.call("save selected simulated final state", "rpgcobo_runtime_save_all")
        recorder.call("reload selected simulated final state", "rpgcobo_runtime_reload_tool")
    time.sleep(5)
    with RPGCoboClient(confirm_changes=False) as client:
        recorder = Recorder(results, "selected-final-reload", client)
        recorder.call("reopen selected simulated final", "rpgcobo_editor_open_data", {"id": outcome["map_id"]})
        time.sleep(0.5)
        info = recorder.call("inspect selected simulated final", "rpgcobo_editor_map_get_info")
        final_validation = recorder.call(
            "validate selected simulated final",
            "rpgcobo_map_validate",
            {"max_traversability_cells": 65536},
        )
        if info["name"] != outcome["name"] or info["counts"]["events"] < 9 or final_validation["errors"]:
            raise RuntimeError("Experiment 005 final reload verification failed")
        capture = capture_settled(recorder, "capture selected simulated final")
        final_path = copy_capture(capture["path"], f"{outcome['map_id']}-{selected}-final.png")

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
    results["completed"] = True
    results["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
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
    parser.add_argument("stage", choices=("simulate", "build", "verify", "score", "refine", "finalize"))
    args = parser.parse_args()
    if args.stage == "simulate":
        return simulate()
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
