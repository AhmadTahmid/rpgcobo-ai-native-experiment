from __future__ import annotations

import json
import os
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from ai_native_mcp import MCPError, RPGCoboClient  # noqa: E402


REQUIRED_TOOLS = {
    "rpgcobo_editor_map_get_info",
    "rpgcobo_editor_map_get_size",
    "rpgcobo_editor_map_list_events",
    "rpgcobo_editor_map_get_event",
    "rpgcobo_editor_map_list_assets",
    "rpgcobo_editor_map_get_region_summary",
    "rpgcobo_editor_map_get_surface_grid",
    "rpgcobo_project_search_assets",
    "rpgcobo_project_get_asset_info",
    "rpgcobo_project_search_map_materials",
    "rpgcobo_editor_map_set_block",
    "rpgcobo_editor_map_fill_region",
    "rpgcobo_editor_map_clear_region",
    "rpgcobo_editor_map_place_asset",
    "rpgcobo_editor_map_remove_free_block",
    "rpgcobo_editor_map_move_free_block",
    "rpgcobo_editor_map_place_free_block",
    "rpgcobo_editor_map_create_path",
    "rpgcobo_editor_map_create_pond",
    "rpgcobo_editor_map_create_forest_patch",
    "rpgcobo_editor_map_create_clearing",
    "rpgcobo_editor_map_create_event",
    "rpgcobo_editor_map_update_event",
    "rpgcobo_editor_map_set_player_start",
    "rpgcobo_editor_map_set_name",
    "rpgcobo_editor_map_undo",
    "rpgcobo_map_validate",
    "rpgcobo_editor_map_capture_view",
    "rpgcobo_debug_get_player_state",
    "rpgcobo_debug_player_move",
    "rpgcobo_debug_player_interact",
    "rpgcobo_change_rollback",
}


class StaticContractTests(unittest.TestCase):
    def test_agent_modules_are_loaded(self) -> None:
        load = (ROOT / "project/plugin/rpgtools/mcp/load.sk").read_text(encoding="utf-8")
        for module in (
            "AgentNative.sk",
            "AgentInspect.sk",
            "AgentAssetTools.sk",
            "AgentMapTools.sk",
            "AgentValidation.sk",
            "AgentPlaytest.sk",
        ):
            self.assertIn(module, load)

    def test_required_tool_names_are_unique_and_registered(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "project/plugin/rpgtools/mcp").glob("Agent*.sk")
        )
        names = re.findall(r'name\s*=\s*"(rpgcobo_[^"]+)"', source)
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(REQUIRED_TOOLS.issubset(names), REQUIRED_TOOLS.difference(names))

    def test_asset_metadata_overlay_is_valid_and_well_formed(self) -> None:
        data = json.loads((ROOT / "project/agent/asset-metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertIsInstance(data["assets"], dict)
        for asset_id, metadata in data["assets"].items():
            self.assertRegex(asset_id, r"^(MA|CV)\d{3}$")
            self.assertIsInstance(metadata.get("category"), str)
            self.assertTrue(metadata.get("tags"))

    def test_no_agent_code_reads_bw_files_as_bytes(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "project/plugin/rpgtools/mcp").glob("Agent*.sk")
        )
        self.assertNotRegex(source, r'FileRef\([^\n]*\.bw')
        self.assertIn("ObjectInput.decode", source)
        self.assertIn("BlockOperation", source)

    def test_event_colors_follow_the_upstream_palette(self) -> None:
        source = (ROOT / "project/plugin/rpgtools/mcp/AgentMapTools.sk").read_text(encoding="utf-8")
        self.assertIn("length(::evcolorlist)-1", source)
        self.assertNotIn('desc="editor color 0-7"', source)

    def test_editor_operation_wrapper_reverts_throwing_redo(self) -> None:
        source = (ROOT / "project/plugin/rpgtools/mcp/AgentNative.sk").read_text(encoding="utf-8")
        self.assertIn("catch(ex)", source)
        self.assertIn("if(ed.op.undocurs==oldcursor+1)try{ed.op.undo();}", source)


@unittest.skipUnless(os.environ.get("RPGCOBO_LIVE_TEST") == "1", "set RPGCOBO_LIVE_TEST=1 with the editor running")
class LiveMCPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = RPGCoboClient(confirm_changes=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()

    def test_01_registration(self) -> None:
        names = {tool["name"] for tool in self.client.tools()}
        self.assertTrue(REQUIRED_TOOLS.issubset(names), REQUIRED_TOOLS.difference(names))

    def test_02_map_inspection_and_invalid_arguments(self) -> None:
        info = self.client.call("rpgcobo_editor_map_get_info")
        self.assertRegex(info["map_id"], r"^M\d{3}$")
        self.assertGreater(info["size"]["width"], 0)
        with self.assertRaises(MCPError):
            self.client.call(
                "rpgcobo_editor_map_get_region_summary",
                {"x": -1, "z": 0, "width": 1, "depth": 1},
            )

    def test_03_asset_lookup_and_validation(self) -> None:
        search = self.client.call(
            "rpgcobo_project_search_assets", {"query": "", "types": "map_asset", "limit": 3}
        )
        self.assertGreater(search["total"], 0)
        asset = self.client.call("rpgcobo_project_get_asset_info", {"id": search["assets"][0]["id"]})
        self.assertEqual(asset["type"], "map_asset")
        validation = self.client.call("rpgcobo_map_validate", {"max_traversability_cells": 65536})
        self.assertIn("errors", validation)
        self.assertIn("warnings", validation)
        self.assertIn("metrics", validation)

    def test_04_mutation_inspection_and_rollback(self) -> None:
        info = self.client.call("rpgcobo_editor_map_get_info")
        size = info["size"]
        spawn = info.get("player_start", {}).get("pos", [size["width"] / 4, 1, size["depth"] / 4])
        sx = max(0, min(size["width"] - 8, int(spawn[0] * 2) - 4))
        sz = max(0, min(size["depth"] - 8, int(spawn[2] * 2) - 4))
        neighborhood = self.client.call(
            "rpgcobo_editor_map_get_region_summary",
            {"x": sx, "z": sz, "width": 8, "depth": 8},
        )
        block_id = neighborhood["dominant_surface"]["block"]["id"]
        point = {"x": size["width"] - 1, "y": size["height"] - 1, "z": size["depth"] - 1}
        before = self.client.call(
            "rpgcobo_editor_map_get_region_summary",
            {"x": point["x"], "z": point["z"], "width": 1, "depth": 1, "y_min": point["y"], "y_max": point["y"]},
        )
        change = self.client.call("rpgcobo_editor_map_set_block", {**point, "block": block_id})
        after = self.client.call(
            "rpgcobo_editor_map_get_region_summary",
            {"x": point["x"], "z": point["z"], "width": 1, "depth": 1, "y_min": point["y"], "y_max": point["y"]},
        )
        self.assertNotEqual(before["occupied_blocks"], after["occupied_blocks"])
        rolled_back = self.client.call("rpgcobo_change_rollback", {"change_id": change["changeid"]})
        self.assertTrue(rolled_back["rolledback"])
        restored = self.client.call(
            "rpgcobo_editor_map_get_region_summary",
            {"x": point["x"], "z": point["z"], "width": 1, "depth": 1, "y_min": point["y"], "y_max": point["y"]},
        )
        self.assertEqual(before["occupied_blocks"], restored["occupied_blocks"])

    def test_05_seeded_path_is_deterministic(self) -> None:
        info = self.client.call("rpgcobo_editor_map_get_info")
        size = info["size"]
        spawn = info.get("player_start", {}).get("pos", [size["width"] / 4, 1, size["depth"] / 4])
        sx = max(4, min(size["width"] - 16, int(spawn[0] * 2) - 4))
        sz = max(4, min(size["depth"] - 8, int(spawn[2] * 2)))
        region_args = {"x": sx - 4, "z": sz - 4, "width": 20, "depth": 12}
        baseline = self.client.call("rpgcobo_editor_map_get_region_summary", region_args)
        dominant = baseline["dominant_surface"]["block"]["id"]
        alternatives = [x["block"]["id"] for x in baseline["block_usage"] if x["block"]["id"] != dominant]
        if not alternatives:
            self.skipTest("inspection region contains no alternate authored block material")
        args = {
            "start_x": sx,
            "start_z": sz,
            "end_x": sx + 10,
            "end_z": sz,
            "width": 1,
            "block": alternatives[0],
            "curvature": 0.45,
            "seed": 1729,
        }
        first = self.client.call("rpgcobo_editor_map_create_path", args)
        first_summary = self.client.call("rpgcobo_editor_map_get_region_summary", region_args)
        self.client.call("rpgcobo_change_rollback", {"change_id": first["changeid"]})
        second = self.client.call("rpgcobo_editor_map_create_path", args)
        second_summary = self.client.call("rpgcobo_editor_map_get_region_summary", region_args)
        self.client.call("rpgcobo_change_rollback", {"change_id": second["changeid"]})
        self.assertEqual(first["details"]["changed_cells"], second["details"]["changed_cells"])
        self.assertEqual(first_summary["surface_blocks"], second_summary["surface_blocks"])

    def test_06_invalid_event_palette_is_rejected_without_mutation(self) -> None:
        before = self.client.call("rpgcobo_editor_map_list_events", {"offset": 0, "limit": 500})
        info = self.client.call("rpgcobo_editor_map_get_info")
        spawn = info.get("player_start", {}).get("pos", [1, 1, 1])
        with self.assertRaises(MCPError):
            self.client.call(
                "rpgcobo_editor_map_create_event",
                {
                    "role": "villager",
                    "x": int(spawn[0] * 2),
                    "y": max(0, int(spawn[1] * 2)),
                    "z": int(spawn[2] * 2),
                    "color": 6,
                },
            )
        after = self.client.call("rpgcobo_editor_map_list_events", {"offset": 0, "limit": 500})
        self.assertEqual(before["total"], after["total"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
