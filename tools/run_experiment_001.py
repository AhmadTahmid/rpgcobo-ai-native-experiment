#!/usr/bin/env python3
"""Build the first controlled AI-native world slice on the M980 flat template.

Run once on a clean sample project with RPG-Cobo already open.  Every geometry
change goes through a dedicated MCP tool and RPG-Cobo's editor/BlockOperation
stack; this script never reads or writes a .bw file.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from ai_native_mcp import RPGCoboClient


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "work/agent-output/experiment-001-results.json"


def main() -> int:
    results: dict[str, Any] = {"experiment": "001", "map_id": "M980", "operations": [], "failures": []}

    with RPGCoboClient(confirm_changes=True) as client:
        def run(label: str, tool: str, args: dict[str, Any] | None = None, required: bool = True) -> Any:
            try:
                value = client.call(tool, args)
                recorded = value
                if isinstance(value, dict) and any(
                    item.get("type") == "image" for item in value.get("content", []) if isinstance(item, dict)
                ):
                    recorded = {
                        "content": [
                            {
                                "type": item.get("type"),
                                "mimeType": item.get("mimeType"),
                                "encoded_bytes": len(item.get("data", "")),
                            }
                            for item in value["content"]
                        ]
                    }
                results["operations"].append({"label": label, "tool": tool, "arguments": args or {}, "result": recorded})
                return value
            except Exception as exc:  # preserve later independent observations
                results["failures"].append(
                    {"label": label, "tool": tool, "arguments": args or {}, "error": str(exc), "required": required}
                )
                if required:
                    raise
                return None

        run("open template", "rpgcobo_editor_open_data", {"id": "M980"})
        time.sleep(1)
        info = run("inspect map", "rpgcobo_editor_map_get_info")
        if info["map_id"] != "M980":
            raise RuntimeError(f"M980 did not become current; current map is {info['map_id']}")

        work_region = {"x": 16, "z": 16, "width": 64, "depth": 64}
        before = run("inspect work region before", "rpgcobo_editor_map_get_region_summary", work_region)
        if before["free_blocks"]["total"] or before["events"]:
            raise RuntimeError("Experiment 001 requires a clean M980 template/work region; refusing to duplicate content")
        ground = before["dominant_surface"]["block"]["id"]
        surface_y = before["elevation"]["max"]

        floor_search = run(
            "discover path materials",
            "rpgcobo_project_search_map_materials",
            {"query": "floor", "kind": "block", "limit": 100},
        )
        path_candidates = [
            material for material in floor_search["materials"]
            if not material["hidden"] and material["id"] != ground
        ]
        if not path_candidates:
            raise RuntimeError("No authored alternate floor material was discoverable")
        path_block = path_candidates[0]["id"]

        water_search = run(
            "discover water materials",
            "rpgcobo_project_search_map_materials",
            {"query": "water", "kind": "block", "limit": 20},
        )
        water_block = next(material["id"] for material in water_search["materials"] if not material["hidden"])

        tree_search = run(
            "discover tree variations",
            "rpgcobo_project_search_map_materials",
            {"query": "tree", "kind": "free_block", "limit": 100},
        )
        trees = [
            material for material in tree_search["materials"]
            if not material["hidden"] and material.get("model", [""])[0] == "tree1"
        ]
        trees = sorted(trees, key=lambda material: material["variation"])[:4]
        if not trees:
            raise RuntimeError("No authored tree free-block variations were discoverable")
        tree_variants = ",".join(str(material["variation"]) for material in trees)
        tree_type = trees[0]["fbtype"]

        landmark = run("inspect church landmark", "rpgcobo_project_get_asset_info", {"id": "MA008"})

        run(
            "winding path",
            "rpgcobo_editor_map_create_path",
            {
                "start_x": 18, "start_z": 51, "end_x": 73, "end_z": 43,
                "width": 3, "block": path_block, "curvature": 0.32, "seed": 1001,
            },
        )
        run(
            "pond",
            "rpgcobo_editor_map_create_pond",
            {
                "center_x": 43, "center_z": 62, "radius": 7,
                "water_block": water_block, "irregularity": 0.28, "seed": 1002,
            },
        )
        run(
            "raised feature",
            "rpgcobo_editor_map_fill_region",
            {
                "x": 64, "y": surface_y + 1, "z": 20,
                "width": 8, "height": 3, "depth": 8, "block": ground,
            },
        )
        run(
            "forest patch",
            "rpgcobo_editor_map_create_forest_patch",
            {
                "x": 18, "z": 18, "width": 30, "depth": 26,
                "density": 0.72, "clearing_rate": 0.04, "min_spacing": 4,
                "tree_fbtype": tree_type, "tree_variants": tree_variants,
                "max_count": 26, "seed": 1003,
            },
        )
        run(
            "forest clearing",
            "rpgcobo_editor_map_create_clearing",
            {
                "x": 28, "z": 26, "width": 10, "depth": 10,
                "tree_fbtype": tree_type, "ground_block": ground,
            },
        )
        run(
            "church landmark",
            "rpgcobo_editor_map_place_asset",
            {"asset_id": landmark["id"], "x": 61, "y": surface_y + 1, "z": 47, "rotation": 0},
        )
        run(
            "player start",
            "rpgcobo_editor_map_set_player_start",
            {"x": 20, "y": surface_y + 1, "z": 51, "rotation": 1},
        )
        run(
            "guide NPC",
            "rpgcobo_editor_map_create_event",
            {
                "role": "villager", "x": 27, "y": surface_y + 1, "z": 49,
                "rotation": 3, "name": "*agent-guide", "model_resource_id": "CV004",
                "message": "The old path bends around the pond toward the church.", "color": 2,
            },
            required=False,
        )

        run("inspect work region after", "rpgcobo_editor_map_get_region_summary", work_region)
        run("list generated free blocks", "rpgcobo_editor_map_list_assets", {**work_region, "limit": 200})
        run("list generated events", "rpgcobo_editor_map_list_events", {"offset": 0, "limit": 100})
        run("validate", "rpgcobo_map_validate", {"max_traversability_cells": 65536})
        run("capture overview", "rpgcobo_editor_map_capture_view")
        run("save", "rpgcobo_runtime_save_all")

        debug = run(
            "start playtest", "rpgcobo_debug_start",
            {"saveslot": -1, "debugitems": False, "debugskills": False, "debuglv": 0},
            required=False,
        )
        if debug is not None:
            state = None
            for _ in range(10):
                time.sleep(0.5)
                state = run("poll player state", "rpgcobo_debug_get_player_state", required=False)
                if state and state.get("running"):
                    break
            if state and state.get("running"):
                run("move player", "rpgcobo_debug_player_move", {"dx": 1.5, "dz": 0.0, "speed": 3.0}, required=False)
                time.sleep(0.75)
                run("observe moved player", "rpgcobo_debug_get_player_state", required=False)
                run("attempt interaction", "rpgcobo_debug_player_interact", required=False)
                run("capture runtime", "rpgcobo_debug_screenshot", required=False)
            run("stop playtest", "rpgcobo_debug_stop", required=False)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "operations": len(results["operations"]), "failures": results["failures"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
