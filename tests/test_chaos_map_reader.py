"""
Unit tests for Mini-map Parser and DAG Builder (`chaos_map_reader.py`).
"""
import os
import unittest
import cv2
import numpy as np

from chaos_map_reader import (
    extract_minimap,
    is_chaos_map_screen,
    classify_node_type,
    parse_chaos_minimap,
)
from chaos_pathfinder import (
    ChaosNodeType,
    IslandChoice,
    select_best_island,
)


class TestChaosMapReader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_dir = os.path.join(os.path.dirname(__file__), "fixtures")
        cls.map_3_path = os.path.join(cls.fixture_dir, "chaos_map_3_islands.png")
        cls.map_1_path = os.path.join(cls.fixture_dir, "chaos_map_1_island.png")
        cls.leave_path = os.path.join(cls.fixture_dir, "chaos_reward_leave.png")

        cls.img_map_3 = cv2.imread(cls.map_3_path)
        cls.img_map_1 = cv2.imread(cls.map_1_path)
        cls.img_leave = cv2.imread(cls.leave_path)

    def test_extract_minimap(self):
        """Test extraction of 640x320 minimap from 1600x900 screen."""
        self.assertIsNotNone(self.img_map_3)
        crop = extract_minimap(self.img_map_3)
        self.assertIsNotNone(crop)
        self.assertEqual(crop.shape, (320, 640, 3))

    def test_is_chaos_map_screen(self):
        """Test recognition of Chaos map screen vs other screens."""
        self.assertTrue(is_chaos_map_screen(self.img_map_3))
        self.assertTrue(is_chaos_map_screen(self.img_map_1))
        self.assertFalse(is_chaos_map_screen(self.img_leave))
        self.assertFalse(is_chaos_map_screen(np.zeros((900, 1600, 3), dtype=np.uint8)))

    def test_classify_templates(self):
        """Test node classification against saved templates."""
        tpl_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
        
        sword = cv2.imread(os.path.join(tpl_dir, "chaos_node_sword.png"))
        if sword is not None:
            ntype, _ = classify_node_type(sword)
            self.assertEqual(ntype, ChaosNodeType.NORMAL)

        fire = cv2.imread(os.path.join(tpl_dir, "chaos_node_fire.png"))
        if fire is not None:
            ntype, _ = classify_node_type(fire)
            self.assertEqual(ntype, ChaosNodeType.REST)

        event = cv2.imread(os.path.join(tpl_dir, "chaos_node_event.png"))
        if event is not None:
            ntype, _ = classify_node_type(event)
            self.assertEqual(ntype, ChaosNodeType.EVENT)

        waypoint = cv2.imread(os.path.join(tpl_dir, "chaos_node_waypoint.png"))
        if waypoint is not None:
            ntype, _ = classify_node_type(waypoint)
            self.assertEqual(ntype, ChaosNodeType.OTHER)

    def test_parse_3_islands_map(self):
        """Test parsing of 3-islands map and pathfinding to Boss."""
        roots, adj, nodes, boss_ids = parse_chaos_minimap(self.img_map_3)

        self.assertIn(IslandChoice.TOP, roots)
        self.assertIn(IslandChoice.MIDDLE, roots)
        self.assertIn(IslandChoice.BOTTOM, roots)
        self.assertIn("boss", boss_ids)

        # Pathfinding with high HP (100%)
        best_island_high, evals_high = select_best_island(roots, adj, nodes, boss_ids, 1.0)
        self.assertIsNotNone(best_island_high)
        self.assertTrue(evals_high[best_island_high].is_available)
        self.assertIsNotNone(evals_high[best_island_high].best_path)
        self.assertEqual(evals_high[best_island_high].best_path.nodes[-1].node_id, "boss")

        # Pathfinding with low HP (45%)
        best_island_low, evals_low = select_best_island(roots, adj, nodes, boss_ids, 0.45)
        self.assertIsNotNone(best_island_low)
        self.assertTrue(evals_low[best_island_low].is_available)
        self.assertIsNotNone(evals_low[best_island_low].best_path)

    def test_parse_1_island_map(self):
        """Test parsing of 1-island map (forced single branch)."""
        roots, adj, nodes, boss_ids = parse_chaos_minimap(self.img_map_1)

        # Only Middle island should exist
        self.assertIn(IslandChoice.MIDDLE, roots)
        self.assertNotIn(IslandChoice.TOP, roots)
        self.assertNotIn(IslandChoice.BOTTOM, roots)

        best_island, evals = select_best_island(roots, adj, nodes, boss_ids, 1.0)
        self.assertEqual(best_island, IslandChoice.MIDDLE)
        self.assertTrue(evals[IslandChoice.MIDDLE].is_available)
        self.assertIsNotNone(evals[IslandChoice.MIDDLE].best_path)
        self.assertEqual(evals[IslandChoice.MIDDLE].best_path.nodes[-1].node_id, "boss")

    def test_row_to_island_choice(self):
        """Test row index to IslandChoice mapping."""
        from chaos_map_reader import _row_to_island_choice
        self.assertEqual(_row_to_island_choice(1, 85), IslandChoice.TOP)
        self.assertEqual(_row_to_island_choice(3, 198), IslandChoice.MIDDLE)
        self.assertEqual(_row_to_island_choice(4, 254), IslandChoice.BOTTOM)
        self.assertEqual(_row_to_island_choice(0, 30), IslandChoice.TOP)

    def test_parse_2_islands_map_fixture(self):
        """Test parsing of 2-islands fixture map."""
        map_2_path = os.path.join(self.fixture_dir, "chaos_map_2_islands.png")
        if os.path.exists(map_2_path):
            img_map_2 = cv2.imread(map_2_path)
            roots, adj, nodes, boss_ids = parse_chaos_minimap(img_map_2)
            self.assertEqual(len(roots), 2)
            self.assertIn(IslandChoice.TOP, roots)
            self.assertIn(IslandChoice.BOTTOM, roots)

    def test_detect_3d_island_coords(self):
        """Test dynamic 3D detection on fixture images."""
        from chaos_map_reader import detect_3d_island_coords

        # 3 islands map
        coords_3 = detect_3d_island_coords(self.img_map_3, [IslandChoice.TOP, IslandChoice.MIDDLE, IslandChoice.BOTTOM])
        self.assertEqual(len(coords_3), 3)
        self.assertIn(IslandChoice.TOP, coords_3)
        self.assertIn(IslandChoice.MIDDLE, coords_3)
        self.assertIn(IslandChoice.BOTTOM, coords_3)
        # Verify Y increases from TOP to BOTTOM
        self.assertLess(coords_3[IslandChoice.TOP][1], coords_3[IslandChoice.MIDDLE][1])
        self.assertLess(coords_3[IslandChoice.MIDDLE][1], coords_3[IslandChoice.BOTTOM][1])

        # 1 island map
        coords_1 = detect_3d_island_coords(self.img_map_1, [IslandChoice.MIDDLE])
        self.assertEqual(len(coords_1), 1)
        self.assertIn(IslandChoice.MIDDLE, coords_1)

    def test_parse_diagonal_minimap_fixture(self):
        """Test parsing of diagonal branches and single island choice on live capture."""
        diag_path = os.path.join(self.fixture_dir, "chaos_map_diagonal.png")
        if os.path.exists(diag_path):
            img_diag = cv2.imread(diag_path)
            roots, adj, nodes, boss_ids = parse_chaos_minimap(img_diag)
            self.assertEqual(len(roots), 1)
            self.assertIn(IslandChoice.TOP, roots)
            best_island, evals = select_best_island(roots, adj, nodes, boss_ids, 1.0)
            self.assertEqual(best_island, IslandChoice.TOP)
            self.assertTrue(evals[IslandChoice.TOP].is_available)
            self.assertIsNotNone(evals[IslandChoice.TOP].best_path)
    def test_seraph_boss_map(self):
        """Test Seraph angel boss map with 4 columns and bottom pin position."""
        from detector import ScreenDetector
        from config import State

        seraph_path = os.path.join(self.fixture_dir, "chaos_map_seraph.png")
        if os.path.exists(seraph_path):
            img_seraph = cv2.imread(seraph_path)
            # 1. Verification of screen detection
            self.assertTrue(is_chaos_map_screen(img_seraph))
            det = ScreenDetector()
            st, _ = det.detect(img_seraph)
            self.assertEqual(st, State.CHAOS_MAP)

            # 2. Verification of minimap parsing and pathfinding
            roots, adj, nodes, boss_ids = parse_chaos_minimap(img_seraph)
            self.assertEqual(len(roots), 2)
            self.assertIn(IslandChoice.MIDDLE, roots)
            self.assertIn(IslandChoice.BOTTOM, roots)
            best_island, evals = select_best_island(roots, adj, nodes, boss_ids, 100.0)
            self.assertIsNotNone(best_island)
            self.assertTrue(evals[best_island].is_available)
            self.assertEqual(evals[best_island].best_path.nodes[-1].node_id, "boss")


if __name__ == "__main__":
    unittest.main()

