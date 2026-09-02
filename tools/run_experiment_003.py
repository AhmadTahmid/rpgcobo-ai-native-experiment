#!/usr/bin/env python3
"""Experiment 003: autonomously compose a town on a template-free flat map.

M979 is created by ``rpgcobo_project_create_blank_map`` through RPG-Cobo's
BlockWorld serializer.  This driver accepts only that verified uniform baseline,
discovers all authored assets/materials semantically, derives the layout from map
and asset dimensions, and leaves the first build unsaved for visual review.

No serialized .bw file is read, copied, restored, or patched by this driver.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import time
from pathlib import Path
from typing import Any

from ai_native_mcp import RPGCoboClient


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "work/agent-output"
RESULTS_PATH = OUTPUT_DIR / "experiment-003-results.json"
MAP_ID = "M979"
TOWN_NAME = "Linden Crossing"

BRIEF = {
    "name": TOWN_NAME,
    "intent": "Test autonomous town composition from an engine-created uniform plane rather than adaptation of a human-laid map.",
    "baseline_contract": {
        "map_id": MAP_ID,
        "size": [128, 64, 128],
        "occupied_blocks": 16384,
        "free_blocks": 0,
        "events": 0,
        "source_map": None,
        "source_asset": None,
        "template_copied": False,
    },
    "authorship_boundary": {
        "agent_generated": [
            "town plan and normalized spatial layout",
            "road hierarchy, plaza, reflecting pool, vegetation zones, and prop positions",
            "asset selection by semantic query",
            "building placement, inhabitants, dialogue, spawn, validation, and playtest",
        ],
        "human_authored_inputs": [
            "RPG-Cobo engine and editor",
            "block/free-block vocabulary, building assets, character models, textures, and animation",
            "RPGSystem default map properties",
        ],
    },
    "success_criteria": [
        "Baseline is exactly one uniform ground layer with no objects or events.",
        "Eight semantically distinct buildings form legible civic, commercial, and residential zones.",
        "A primary cross, service streets, plaza, reflecting pool, lighting, planting, and edge vegetation are generated.",
        "Nine contextual inhabitants including an entry guide are placed from discovered character assets.",
        "Validation has zero errors before save and after reload, followed by a runtime interaction test.",
    ],
}

BUILDINGS = [
    ("town hall", "mayor", "Welcome to Linden Crossing. The town grew around this square, one careful line at a time."),
    ("church", "priest", "The reflecting pool is new, but the bells already make it feel remembered."),
    ("shop", "merchant", "Market day follows the east-west road. You cannot miss it."),
    ("warehouse", "farmer", "Crates arrive by the north road and leave before the square gets busy."),
    ("apartment", "resident", "The linden trees make this the coolest street in summer."),
    ("large house", "bard", "A town is roads, roofs, and the stories people tell between them."),
    ("brick house", "old man", "The paving is fresh. Give it a season and it will belong here."),
    ("wooden house", "boy", "I can race from the south lane to the pool without crossing the grass!"),
]


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


def new_results() -> dict[str, Any]:
    return {
        "experiment": "003",
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


def copy_capture(source: str, name: str) -> str:
    destination = OUTPUT_DIR / name
    shutil.copy2(ROOT / source, destination)
    return str(destination)


def choose_asset(recorder: Recorder, query: str, resource_type: str) -> dict[str, Any]:
    matches = recorder.call(
        f"discover {query} {resource_type}",
        "rpgcobo_project_search_assets",
        {"query": query, "types": resource_type, "limit": 20},
    )["assets"]
    if not matches:
        raise RuntimeError(f"No {resource_type} discovered for semantic query {query!r}")
    selected = matches[0]
    if resource_type == "map_asset":
        selected = recorder.call(
            f"inspect selected {query}", "rpgcobo_project_get_asset_info", {"id": selected["id"]}
        )
    return selected


def choose_material(recorder: Recorder, query: str, kind: str) -> dict[str, Any]:
    materials = recorder.call(
        f"discover {query} {kind} material",
        "rpgcobo_project_search_map_materials",
        {"query": query, "kind": kind, "limit": 50},
    )["materials"]
    visible = [item for item in materials if not item.get("hidden")]
    if not visible:
        raise RuntimeError(f"No visible {kind} material discovered for {query!r}")
    return visible[0]


def pair_row(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
    width: int,
    center_x: int,
    corridor_half_width: int,
    z: int,
    margin: int,
    gap: int,
) -> list[dict[str, Any]]:
    left_total = sum(item["bounds"]["size"][0] for item in left) + gap * (len(left) - 1)
    right_total = sum(item["bounds"]["size"][0] for item in right) + gap * (len(right) - 1)
    left_available_end = center_x - corridor_half_width - gap
    left_x = max(margin, left_available_end - left_total)
    right_x = center_x + corridor_half_width + gap
    if right_x + right_total > width - margin:
        right_x = width - margin - right_total
    placements: list[dict[str, Any]] = []
    for side, items, start in (("west", left, left_x), ("east", right, right_x)):
        x = start
        for asset in items:
            aw, ah, ad = asset["bounds"]["size"]
            placements.append(
                {
                    "query": asset["selection_query"],
                    "asset_id": asset["id"],
                    "side": side,
                    "origin": [x, 1, z],
                    "rect": [x, z, aw, ad],
                    "asset_size": [aw, ah, ad],
                }
            )
            x += aw + gap
    return placements


def build() -> int:
    results = new_results()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with RPGCoboClient(confirm_changes=True) as client:
        recorder = Recorder(results, "build", client)
        try:
            recorder.call("open template-free baseline", "rpgcobo_editor_open_data", {"id": MAP_ID})
            time.sleep(0.5)
            info = recorder.call("verify exact blank baseline", "rpgcobo_editor_map_get_info")
            expected = BRIEF["baseline_contract"]
            actual_size = [info["size"]["width"], info["size"]["height"], info["size"]["depth"]]
            if (
                info["map_id"] != MAP_ID
                or actual_size != expected["size"]
                or info["counts"]["blocks"] != expected["occupied_blocks"]
                or info["counts"]["free_blocks"] != 0
                or info["counts"]["events"] != 0
            ):
                raise RuntimeError(f"Refusing non-blank baseline: {info}")
            baseline_validation = recorder.call(
                "validate blank baseline", "rpgcobo_map_validate", {"max_traversability_cells": 65536}
            )
            if baseline_validation["errors"]:
                raise RuntimeError(f"Blank baseline validation failed: {baseline_validation['errors']}")
            before = recorder.call("capture true blank baseline", "rpgcobo_editor_map_capture_view")
            results["artifacts"]["before"] = copy_capture(before["path"], "M979-town-before.png")

            width, height, depth = actual_size
            cx, cz = width // 2, depth // 2
            assets: list[dict[str, Any]] = []
            for query, _, _ in BUILDINGS:
                asset = choose_asset(recorder, query, "map_asset")
                asset["selection_query"] = query
                assets.append(asset)

            road = choose_material(recorder, "brick2", "block")
            plaza = choose_material(recorder, "stone2", "block")
            water = choose_material(recorder, "water1", "block")
            lamp = choose_material(recorder, "streetlamp", "free_block")
            flower = choose_material(recorder, "flowerbed", "free_block")
            bench = choose_material(recorder, "bench", "free_block")
            barrel = choose_material(recorder, "barrel", "free_block")
            trees = recorder.call(
                "discover authored edge trees",
                "rpgcobo_project_search_map_materials",
                {"query": "tree1", "kind": "free_block", "limit": 20},
            )["materials"]
            tree_variants = [
                item["variation"]
                for item in trees
                if not item.get("hidden") and item.get("fbtype") == 20
            ][:4]
            if not tree_variants:
                raise RuntimeError("No authored tree variations discovered")

            road_block = road["id"]
            corridor_half = 4
            north_z = max(12, depth * 16 // 100)
            south_z = depth * 66 // 100
            placements = pair_row(
                assets[:2], assets[2:4], width, cx, corridor_half, north_z, 8, 6
            ) + pair_row(
                assets[4:6], assets[6:8], width, cx, corridor_half, south_z, 8, 7
            )
            north_lane = max(item["rect"][1] + item["rect"][3] for item in placements[:4]) + 5
            south_lane = max(item["rect"][1] + item["rect"][3] for item in placements[4:]) + 5
            if south_lane >= depth - 6:
                south_lane = depth - 7

            results["plan"] = {
                "method": "semantic asset discovery plus normalized cross-and-two-service-lanes layout derived from map and asset dimensions",
                "coordinate_source": "map dimensions, asset bounds, fixed proportions, margins, and deterministic packing; no source-map features",
                "center": [cx, cz],
                "materials": {
                    "road": road,
                    "plaza": plaza,
                    "water": water,
                    "lamp": lamp,
                    "flowerbed": flower,
                    "bench": bench,
                    "barrel": barrel,
                    "tree_variants": tree_variants,
                },
                "buildings": placements,
                "roads": {
                    "primary_vertical_x": cx,
                    "primary_horizontal_z": cz,
                    "north_service_z": north_lane,
                    "south_service_z": south_lane,
                },
            }
            results["decisions"].extend(
                [
                    {
                        "decision": "Use a cross-shaped primary network with two service lanes",
                        "reason": "It creates immediate hierarchy and guarantees every packed plot has a short connection without borrowing any template street geometry.",
                    },
                    {
                        "decision": "Keep authored building rotation at zero",
                        "reason": "The current upstream engine lacks the native Block.rotate method expected by BlockOperation; non-zero asset rotation remains disabled for safety.",
                    },
                    {
                        "decision": "Use a small central pool instead of a copied landmark",
                        "reason": "The square needs a visual focus that can be generated from semantic primitives alone.",
                    },
                ]
            )

            recorder.call("name autonomous town", "rpgcobo_editor_map_set_name", {"name": TOWN_NAME})
            for label, start, end, road_width, seed in (
                ("primary north-south boulevard", (cx, 6), (cx, depth - 7), 5, 3001),
                ("primary east-west boulevard", (6, cz), (width - 7, cz), 5, 3002),
                ("north service street", (7, north_lane), (width - 8, north_lane), 3, 3003),
                ("south service street", (7, south_lane), (width - 8, south_lane), 3, 3004),
            ):
                recorder.call(
                    f"create {label}",
                    "rpgcobo_editor_map_create_path",
                    {
                        "start_x": start[0],
                        "start_z": start[1],
                        "end_x": end[0],
                        "end_z": end[1],
                        "width": road_width,
                        "block": road_block,
                        "curvature": 0.0,
                        "seed": seed,
                    },
                )
            plaza_radius = 13
            recorder.call(
                "pave central civic square",
                "rpgcobo_editor_map_fill_region",
                {
                    "x": cx - plaza_radius,
                    "y": 0,
                    "z": cz - plaza_radius,
                    "width": plaza_radius * 2 + 1,
                    "height": 1,
                    "depth": plaza_radius * 2 + 1,
                    "block": plaza["id"],
                },
            )
            recorder.call(
                "create central reflecting pool",
                "rpgcobo_editor_map_create_pond",
                {
                    "center_x": cx,
                    "center_z": cz,
                    "radius": 4,
                    "water_block": water["id"],
                    "water_y": 0,
                    "irregularity": 0.05,
                    "seed": 3030,
                },
            )

            for placement in placements:
                recorder.call(
                    f"place {placement['query']}",
                    "rpgcobo_editor_map_place_asset",
                    {
                        "asset_id": placement["asset_id"],
                        "x": placement["origin"][0],
                        "y": placement["origin"][1],
                        "z": placement["origin"][2],
                        "rotation": 0,
                    },
                )

            connectors: list[dict[str, Any]] = []
            for index, placement in enumerate(placements):
                x, z, aw, ad = placement["rect"]
                lane = north_lane if index < 4 else south_lane
                start = (x + aw // 2, z + ad + 1)
                recorder.call(
                    f"connect {placement['query']} to service street",
                    "rpgcobo_editor_map_create_path",
                    {
                        "start_x": start[0],
                        "start_z": start[1],
                        "end_x": start[0],
                        "end_z": lane,
                        "width": 2,
                        "block": road_block,
                        "curvature": 0.0,
                        "seed": 3100 + index,
                    },
                )
                connectors.append({"query": placement["query"], "start": list(start), "end": [start[0], lane]})
            results["plan"]["connectors"] = connectors

            # The four edge patches are intentionally outside all plots.  Their
            # seeds and bounded counts make this decoration reproducible.
            for label, x, z, patch_w, patch_d, seed in (
                ("north", 4, 3, width - 8, 10, 3201),
                ("south", 4, depth - 13, width - 8, 9, 3202),
                ("west", 3, 16, 7, depth - 32, 3203),
                ("east", width - 10, 16, 7, depth - 32, 3204),
            ):
                recorder.call(
                    f"grow {label} edge grove",
                    "rpgcobo_editor_map_create_forest_patch",
                    {
                        "x": x,
                        "z": z,
                        "width": patch_w,
                        "depth": patch_d,
                        "density": 0.65,
                        "clearing_rate": 0.12,
                        "min_spacing": 5,
                        "tree_fbtype": 20,
                        "tree_variants": ",".join(str(item) for item in tree_variants),
                        "max_count": 48,
                        "seed": seed,
                    },
                    required=False,
                )

            prop_specs = []
            for i, z in enumerate((18, 36, cz - 15, cz + 15, 92, 110)):
                prop_specs.extend(
                    [
                        (f"west boulevard lamp {i + 1}", lamp, cx - 4, z, 0),
                        (f"east boulevard lamp {i + 1}", lamp, cx + 4, z, 2),
                    ]
                )
            prop_specs.extend(
                [
                    ("northwest plaza flowerbed", flower, cx - 10, cz - 10, 0),
                    ("northeast plaza flowerbed", flower, cx + 10, cz - 10, 1),
                    ("southwest plaza flowerbed", flower, cx - 10, cz + 10, 2),
                    ("southeast plaza flowerbed", flower, cx + 10, cz + 10, 3),
                    ("west pool bench", bench, cx - 7, cz, 1),
                    ("east pool bench", bench, cx + 7, cz, 3),
                ]
            )
            warehouse = next(item for item in placements if item["query"] == "warehouse")
            wx, wz, ww, wd = warehouse["rect"]
            prop_specs.extend(
                [
                    ("warehouse barrel one", barrel, wx + ww + 2, wz + wd - 2, 0),
                    ("warehouse barrel two", barrel, wx + ww + 4, wz + wd - 2, 1),
                ]
            )
            for label, material, x, z, rotation in prop_specs:
                recorder.call(
                    f"place {label}",
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

            inhabitants: list[dict[str, Any]] = []
            for index, ((query, character_query, message), connector) in enumerate(zip(BUILDINGS, connectors)):
                character = choose_asset(recorder, character_query, "chara_vox")
                point = connector["end"]
                event = recorder.call(
                    f"create {character_query} inhabitant",
                    "rpgcobo_editor_map_create_event",
                    {
                        "role": "villager",
                        "x": point[0],
                        "y": 2,
                        "z": point[1],
                        "rotation": index % 4,
                        "name": f"*linden-{character_query.replace(' ', '-')}",
                        "model_resource_id": character["id"],
                        "message": message,
                        "color": index % 6,
                    },
                )
                inhabitants.append(
                    {"building": query, "character_query": character_query, "model": character["id"], "position": point, "event": event}
                )

            entry = [8, cz]
            guide = [13, cz]
            recorder.call(
                "set west-gate player start",
                "rpgcobo_editor_map_set_player_start",
                {"x": entry[0], "y": 2, "z": entry[1], "rotation": 0},
            )
            guard_character = choose_asset(recorder, "guard", "chara_vox")
            recorder.call(
                "create west-gate guide",
                "rpgcobo_editor_map_create_event",
                {
                    "role": "villager",
                    "x": guide[0],
                    "y": 2,
                    "z": guide[1],
                    "rotation": 2,
                    "name": "*linden-west-guide",
                    "model_resource_id": guard_character["id"],
                    "message": "Welcome to Linden Crossing. Follow this boulevard to the reflecting pool and civic square.",
                    "color": 1,
                },
            )
            results["plan"]["entry"] = {"player_start": entry, "guide": guide}
            results["plan"]["inhabitants"] = inhabitants

            recorder.call("inventory generated town objects", "rpgcobo_editor_map_list_assets", {"limit": 500})
            recorder.call("inventory generated inhabitants", "rpgcobo_editor_map_list_events", {"limit": 100})
            validation = recorder.call(
                "validate unsaved from-blank draft", "rpgcobo_map_validate", {"max_traversability_cells": 65536}
            )
            if validation["errors"]:
                raise RuntimeError(f"Draft validation errors: {validation['errors']}")
            draft = recorder.call("capture from-blank town draft", "rpgcobo_editor_map_capture_view")
            results["artifacts"]["draft"] = copy_capture(draft["path"], "M979-town-draft.png")
            results["draft_ready_for_visual_review"] = True
        except Exception:
            recorder.rollback_all()
            results["draft_ready_for_visual_review"] = False
            write_results(results)
            raise
    write_results(results)
    print(json.dumps({"status": "draft-ready", "results": str(RESULTS_PATH), "artifacts": results["artifacts"]}, indent=2))
    return 0


def polish() -> int:
    if not RESULTS_PATH.exists():
        raise RuntimeError("Run the Experiment 003 build stage first")
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    with RPGCoboClient(confirm_changes=True) as client:
        recorder = Recorder(results, "visual-review-polish", client)
        info = recorder.call("inspect visually reviewed draft", "rpgcobo_editor_map_get_info")
        if info["map_id"] != MAP_ID or info["counts"]["events"] < 9:
            raise RuntimeError("Experiment 003 draft is not open")
        before = recorder.call(
            "inspect visual-review warnings", "rpgcobo_map_validate", {"max_traversability_cells": 65536}
        )
        removed: list[int] = []
        for warning in before["warnings"]:
            if warning["code"] != "FREE_BLOCK_OUTSIDE_MAP":
                continue
            uid = warning["data"]["uid"]
            recorder.call(
                f"remove out-of-bounds decoration {uid}",
                "rpgcobo_editor_map_remove_free_block",
                {"uid": uid},
            )
            removed.append(uid)

        barrel = results["plan"]["materials"]["barrel"]
        warehouse = next(item for item in results["plan"]["buildings"] if item["query"] == "warehouse")
        wx, wz, _, wd = warehouse["rect"]
        for index, (x, z) in enumerate(((wx - 4, wz + wd // 3), (wx - 4, wz + wd - 2))):
            recorder.call(
                f"retry warehouse barrel {index + 1} after visual review",
                "rpgcobo_editor_map_place_free_block",
                {
                    "fbtype": barrel["fbtype"],
                    "variation": barrel["variation"],
                    "x": x,
                    "y": -1,
                    "z": z,
                    "rotation": index,
                    "allow_overlap": False,
                },
                required=False,
            )

        validation = recorder.call(
            "validate polished unsaved draft", "rpgcobo_map_validate", {"max_traversability_cells": 65536}
        )
        if validation["errors"] or any(w["code"] == "FREE_BLOCK_OUTSIDE_MAP" for w in validation["warnings"]):
            raise RuntimeError(f"Visual-review polish did not clear structural warnings: {validation}")
        capture = recorder.call("capture polished unsaved draft", "rpgcobo_editor_map_capture_view")
        results["artifacts"]["polished_draft"] = copy_capture(capture["path"], "M979-town-draft-polished.png")
        results["visual_review"] = {
            "assessment": "Legible garden-town composition with a strong civic center; more obviously axial and symmetric than the adapted Canalwatch map.",
            "strengths": [
                "clear road hierarchy and central landmark",
                "eight distinct silhouettes with civic/commercial/residential zoning",
                "dense perimeter vegetation frames the playable center",
            ],
            "limitations": [
                "large rectangular lawns and equal setbacks expose the procedural grammar",
                "all building assets share rotation zero because safe rotation is unavailable",
                "the editor overview proves composition, not player-scale collision quality",
            ],
            "corrections": {
                "removed_out_of_bounds_free_block_uids": removed,
                "forest_generator_hardened": True,
                "optional_barrels_retried": True,
            },
        }
    write_results(results)
    print(json.dumps({"status": "polished-draft-ready", "artifacts": results["artifacts"]}, indent=2))
    return 0


def finalize() -> int:
    if not RESULTS_PATH.exists():
        raise RuntimeError("Run the Experiment 003 build stage first")
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    with RPGCoboClient(confirm_changes=True) as client:
        recorder = Recorder(results, "finalize", client)
        info = recorder.call("inspect reviewed from-blank draft", "rpgcobo_editor_map_get_info")
        if info["map_id"] != MAP_ID or info["counts"]["events"] < 9:
            raise RuntimeError("Reviewed Experiment 003 draft is not open")
        validation = recorder.call(
            "validate reviewed from-blank town", "rpgcobo_map_validate", {"max_traversability_cells": 65536}
        )
        if validation["errors"]:
            raise RuntimeError(f"Reviewed town errors: {validation['errors']}")
        reviewed = recorder.call("capture reviewed from-blank town", "rpgcobo_editor_map_capture_view")
        results["artifacts"]["reviewed"] = copy_capture(reviewed["path"], "M979-town-reviewed.png")
        recorder.call("save reviewed from-blank town", "rpgcobo_runtime_save_all")

        debug = recorder.call(
            "start from-blank town playtest",
            "rpgcobo_debug_start",
            {"saveslot": -1, "debugitems": False, "debugskills": False, "debuglv": 0},
            required=False,
        )
        if debug is not None:
            state = None
            for attempt in range(20):
                time.sleep(0.5)
                state = recorder.call(
                    f"poll from-blank runtime {attempt + 1}", "rpgcobo_debug_get_player_state", required=False
                )
                if state and state.get("running"):
                    break
            if state and state.get("running"):
                entry = results["plan"]["entry"]["player_start"]
                guide = results["plan"]["entry"]["guide"]
                recorder.call(
                    "walk toward west-gate guide",
                    "rpgcobo_debug_player_move",
                    {"dx": (guide[0] - entry[0]) * 0.45, "dz": 0, "speed": 3.0},
                    required=False,
                )
                time.sleep(1.0)
                recorder.call("interact with west-gate guide", "rpgcobo_debug_player_interact", required=False)
                time.sleep(1.0)
                shot = recorder.call("capture from-blank runtime", "rpgcobo_debug_screenshot", required=False)
                if isinstance(shot, dict):
                    image_item = next(
                        (item for item in shot.get("content", []) if isinstance(item, dict) and item.get("type") == "image"),
                        None,
                    )
                    if image_item and image_item.get("data"):
                        suffix = ".png" if image_item.get("mimeType") == "image/png" else ".webp"
                        runtime_path = OUTPUT_DIR / f"M979-town-runtime{suffix}"
                        runtime_path.write_bytes(base64.b64decode(image_item["data"]))
                        results["artifacts"]["runtime"] = str(runtime_path)
            recorder.call("stop from-blank playtest", "rpgcobo_debug_stop", required=False)
        recorder.call("reload saved from-blank state", "rpgcobo_runtime_reload_tool")

    time.sleep(5)
    with RPGCoboClient(confirm_changes=False) as client:
        recorder = Recorder(results, "reload-verification", client)
        recorder.call("reopen saved from-blank town", "rpgcobo_editor_open_data", {"id": MAP_ID})
        time.sleep(0.5)
        reloaded_info = recorder.call("inspect reloaded from-blank town", "rpgcobo_editor_map_get_info")
        reloaded_validation = recorder.call(
            "validate reloaded from-blank town", "rpgcobo_map_validate", {"max_traversability_cells": 65536}
        )
        if reloaded_info["name"] != TOWN_NAME or reloaded_info["counts"]["events"] < 9 or reloaded_validation["errors"]:
            raise RuntimeError("Experiment 003 reload verification failed")
        final = recorder.call("capture reload-verified from-blank town", "rpgcobo_editor_map_capture_view")
        results["artifacts"]["final"] = copy_capture(final["path"], "M979-town-final.png")

    results["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    results["completed"] = True
    write_results(results)
    print(
        json.dumps(
            {
                "status": "complete",
                "operations": len(results["operations"]),
                "failures": len(results["failures"]),
                "artifacts": results["artifacts"],
            },
            indent=2,
        )
    )
    return 0


def repair_runtime() -> int:
    """Repair the runtime-only camera default exposed by the first playtest."""
    if not RESULTS_PATH.exists():
        raise RuntimeError("Run the Experiment 003 build/finalize stages first")
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    camera_defaults = {"fovy": 40, "viewport": 12.0, "hpb": [0, 38, 0], "yoffs": 0.5}
    with RPGCoboClient(confirm_changes=True) as client:
        recorder = Recorder(results, "runtime-default-repair", client)
        recorder.call(
            "add missing runtime map defaults",
            "rpgcobo_project_set_database_item",
            {
                "id": MAP_ID,
                "data": {"desc": "", "camwork": camera_defaults, "mapshot": {"crop": [0, 0, 0, 0]}, "vs": 23},
                "override": False,
            },
        )
        recorder.call("reload repaired runtime defaults", "rpgcobo_runtime_reload_tool")

    time.sleep(5)
    with RPGCoboClient(confirm_changes=True) as client:
        recorder = Recorder(results, "runtime-repair-verification", client)
        recorder.call("reopen runtime-repaired town", "rpgcobo_editor_open_data", {"id": MAP_ID})
        time.sleep(0.5)
        info = recorder.call("inspect runtime-repaired town", "rpgcobo_editor_map_get_info")
        if info["properties"].get("camwork") != camera_defaults:
            raise RuntimeError(f"Camera defaults did not persist: {info['properties'].get('camwork')}")
        validation = recorder.call(
            "validate runtime-repaired town", "rpgcobo_map_validate", {"max_traversability_cells": 65536}
        )
        if validation["errors"]:
            raise RuntimeError(f"Runtime repair validation errors: {validation['errors']}")
        recorder.call(
            "start repaired from-blank playtest",
            "rpgcobo_debug_start",
            {"saveslot": -1, "debugitems": False, "debugskills": False, "debuglv": 0},
        )
        state = None
        for attempt in range(20):
            time.sleep(0.5)
            state = recorder.call(
                f"poll repaired runtime {attempt + 1}", "rpgcobo_debug_get_player_state", required=False
            )
            if state and state.get("running"):
                break
        if not state or not state.get("running"):
            raise RuntimeError("Runtime did not reach the running state after camera repair")
        entry = results["plan"]["entry"]["player_start"]
        guide = results["plan"]["entry"]["guide"]
        recorder.call(
            "walk toward repaired west-gate guide",
            "rpgcobo_debug_player_move",
            {"dx": (guide[0] - entry[0]) * 0.45, "dz": 0, "speed": 3.0},
        )
        for attempt in range(10):
            time.sleep(0.3)
            moved = recorder.call(
                f"poll repaired guide approach {attempt + 1}", "rpgcobo_debug_get_player_state", required=False
            )
            if moved and not moved.get("moving"):
                break
        interaction = recorder.call("interact with repaired west-gate guide", "rpgcobo_debug_player_interact")
        time.sleep(1.0)
        shot = recorder.call("capture repaired from-blank runtime", "rpgcobo_debug_screenshot")
        image_item = next(
            (item for item in shot.get("content", []) if isinstance(item, dict) and item.get("type") == "image"),
            None,
        )
        if image_item and image_item.get("data"):
            suffix = ".png" if image_item.get("mimeType") == "image/png" else ".webp"
            runtime_path = OUTPUT_DIR / f"M979-town-runtime{suffix}"
            runtime_path.write_bytes(base64.b64decode(image_item["data"]))
            results["artifacts"]["runtime"] = str(runtime_path)
        recorder.call("stop repaired from-blank playtest", "rpgcobo_debug_stop")

    results["runtime_repair"] = {
        "failure": "Template-free map creation omitted camwork because it lives outside RPGSystem.stageprops; runtime failed at RPGStageState.enter.",
        "fix": "Blank-map creation now supplies the MapToolSel camera defaults, and validation rejects maps without a complete runtime camera record.",
        "verified_running": True,
        "interaction_result": interaction,
    }
    results["runtime_verified"] = True
    write_results(results)
    print(json.dumps({"status": "runtime-repaired-and-verified", "artifacts": results["artifacts"]}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("build", "polish", "finalize", "repair-runtime"))
    args = parser.parse_args()
    if args.stage == "build":
        return build()
    if args.stage == "polish":
        return polish()
    if args.stage == "repair-runtime":
        return repair_runtime()
    return finalize()


if __name__ == "__main__":
    raise SystemExit(main())
