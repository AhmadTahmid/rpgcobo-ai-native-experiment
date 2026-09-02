from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from historical_growth import generate_plan, rects_overlap, validate_non_spatial_brief


class HistoricalGrowthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.briefs = json.loads(
            (ROOT / "docs/ai-native/experiment-005/briefs.json").read_text(encoding="utf-8")
        )
        bindings = json.loads(
            (ROOT / "docs/ai-native/experiment-004/rpgcobo_bindings.json").read_text(encoding="utf-8")
        )
        cls.asset_sizes = {
            **{key: value["expected_size"] for key, value in bindings["buildings"].items()},
            **{key: value["expected_size"] for key, value in bindings["infrastructure"].items()},
        }

    def generate(self, brief: dict) -> dict:
        return generate_plan(brief, self.briefs["shared_constraints"], self.asset_sizes)

    def test_briefs_contain_no_spatial_instructions(self) -> None:
        for brief in self.briefs["settlements"]:
            validate_non_spatial_brief(brief)
        invalid = deepcopy(self.briefs["settlements"][0])
        invalid["cause"]["anchor"] = [0.5, 0.5]
        with self.assertRaisesRegex(ValueError, "Spatial key"):
            validate_non_spatial_brief(invalid)

    def test_same_seed_is_byte_deterministic(self) -> None:
        for brief in self.briefs["settlements"]:
            first = self.generate(brief)
            second = self.generate(brief)
            self.assertEqual(first["checksum"], second["checksum"])
            self.assertEqual(first, second)

    def test_seed_changes_generated_spatial_plan(self) -> None:
        original = self.briefs["settlements"][1]
        changed = deepcopy(original)
        changed["seed"] += 100
        self.assertNotEqual(self.generate(original)["checksum"], self.generate(changed)["checksum"])

    def test_semantic_instances_and_phases_are_complete(self) -> None:
        target = self.briefs["shared_constraints"]["target_building_count"]
        for brief in self.briefs["settlements"]:
            plan = self.generate(brief)
            self.assertEqual(target, len(plan["buildings"]))
            self.assertEqual(len(brief["phases"]), len(plan["phases"]))
            self.assertEqual(0, plan["metrics"]["input_coordinate_fields"])
            self.assertGreater(plan["metrics"]["generated_spatial_records"], 40)
            self.assertGreaterEqual(len(plan["districts"]), 3)
            self.assertTrue(plan["entry"]["player"])
            for building in plan["buildings"]:
                for field in (
                    "id",
                    "role",
                    "binding",
                    "phase",
                    "district",
                    "plot",
                    "rect",
                    "entrance",
                    "frontage_route",
                    "connector_route",
                ):
                    self.assertIn(field, building)

    def test_generated_buildings_and_plots_do_not_overlap(self) -> None:
        clearance = self.briefs["shared_constraints"]["building_clearance_blocks"]
        for brief in self.briefs["settlements"]:
            plan = self.generate(brief)
            for index, building in enumerate(plan["buildings"]):
                for other in plan["buildings"][index + 1 :]:
                    self.assertFalse(rects_overlap(building["rect"], other["rect"], clearance))
            for index, plot in enumerate(plan["plots"]):
                for other in plan["plots"][index + 1 :]:
                    self.assertFalse(rects_overlap(plot["rect"], other["rect"]))

    def test_each_cause_produces_distinct_required_topology(self) -> None:
        plans = {brief["id"]: self.generate(brief) for brief in self.briefs["settlements"]}
        self.assertTrue(any(item["kind"] == "river" for item in plans["river_crossing"]["geography"]))
        self.assertTrue(any(item["kind"] == "bridge" for item in plans["river_crossing"]["infrastructure"]))
        self.assertTrue(any(item["kind"] == "freight" for item in plans["road_confluence"]["districts"]))
        self.assertTrue(any(item["kind"] == "freight_yard" for item in plans["road_confluence"]["surfaces"]))
        self.assertTrue(any(item["kind"] == "court_basin" for item in plans["civic_accretion"]["ponds"]))
        self.assertTrue(any(item["kind"] == "boundary_fragment" for item in plans["civic_accretion"]["infrastructure"]))
        for plan in plans.values():
            self.assertTrue(any(route["status"] == "obsolete" for route in plan["routes"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
