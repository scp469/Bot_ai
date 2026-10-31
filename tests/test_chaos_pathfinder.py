"""
Unit tests for Chaos Pathfinder Core Engine.
Covers Rule A, High/Low HP Scoring, Tie-Breaking, and Safety Fallbacks.
"""
import unittest
from czn_bot.chaos.pathfinder import (
    ChaosNode,
    ChaosNodeType,
    IslandChoice,
    calculate_path_score,
    filter_rule_a,
    select_best_island,
)


class TestRuleA(unittest.TestCase):
    def test_no_elite_is_valid(self):
        nodes = [
            ChaosNode("n1", ChaosNodeType.NORMAL),
            ChaosNode("n2", ChaosNodeType.EVENT),
            ChaosNode("n3", ChaosNodeType.BOSS),
        ]
        valid, reason = filter_rule_a(nodes)
        self.assertTrue(valid)
        self.assertIsNone(reason)

    def test_elite_without_rest_is_rejected(self):
        nodes = [
            ChaosNode("n1", ChaosNodeType.NORMAL),
            ChaosNode("n2", ChaosNodeType.ELITE),
            ChaosNode("n3", ChaosNodeType.EVENT),
            ChaosNode("n4", ChaosNodeType.BOSS),
        ]
        valid, reason = filter_rule_a(nodes)
        self.assertFalse(valid)
        self.assertIn("không có lửa trại", reason)

    def test_elite_before_rest_is_rejected(self):
        nodes = [
            ChaosNode("n1", ChaosNodeType.ELITE),
            ChaosNode("n2", ChaosNodeType.REST),
            ChaosNode("n3", ChaosNodeType.BOSS),
        ]
        valid, reason = filter_rule_a(nodes)
        self.assertFalse(valid)
        self.assertIn("xuất hiện trước lửa trại", reason)

    def test_rest_before_elite_is_valid(self):
        nodes = [
            ChaosNode("n1", ChaosNodeType.REST),
            ChaosNode("n2", ChaosNodeType.ELITE),
            ChaosNode("n3", ChaosNodeType.BOSS),
        ]
        valid, reason = filter_rule_a(nodes)
        self.assertTrue(valid)
        self.assertIsNone(reason)

    def test_one_rest_allows_multiple_elites(self):
        nodes = [
            ChaosNode("n1", ChaosNodeType.REST),
            ChaosNode("n2", ChaosNodeType.ELITE),
            ChaosNode("n3", ChaosNodeType.ELITE),
            ChaosNode("n4", ChaosNodeType.BOSS),
        ]
        valid, reason = filter_rule_a(nodes)
        self.assertTrue(valid)

    def test_event_does_not_substitute_for_rest(self):
        nodes = [
            ChaosNode("n1", ChaosNodeType.EVENT),
            ChaosNode("n2", ChaosNodeType.ELITE),
            ChaosNode("n3", ChaosNodeType.BOSS),
        ]
        valid, reason = filter_rule_a(nodes)
        self.assertFalse(valid)


class TestScoringFormula(unittest.TestCase):
    def test_high_hp_scoring(self):
        # High HP (>= 60%): 3*Elite + 1*Normal - 2*Rest + 0*Other
        nodes = [
            ChaosNode("n1", ChaosNodeType.NORMAL),    # +1
            ChaosNode("n2", ChaosNodeType.ELITE),     # +3
            ChaosNode("n3", ChaosNodeType.REST),      # -2
            ChaosNode("n4", ChaosNodeType.EVENT),     # 0
            ChaosNode("n5", ChaosNodeType.OTHER),     # 0
            ChaosNode("n6", ChaosNodeType.BOSS),      # 0
        ]
        score = calculate_path_score(nodes, is_low_hp=False)
        self.assertEqual(score, 3.0 + 1.0 - 2.0)  # = 2.0

    def test_low_hp_scoring(self):
        # Low HP (< 60%): 5*Rest + 2*Event - 10*Elite + 0*Normal + 0*Other
        nodes = [
            ChaosNode("n1", ChaosNodeType.REST),      # +5
            ChaosNode("n2", ChaosNodeType.EVENT),     # +2
            ChaosNode("n3", ChaosNodeType.NORMAL),    # 0
            ChaosNode("n4", ChaosNodeType.ELITE),     # -10
            ChaosNode("n5", ChaosNodeType.BOSS),      # 0
        ]
        score = calculate_path_score(nodes, is_low_hp=True)
        self.assertEqual(score, 5.0 + 2.0 - 10.0)  # = -3.0


class TestIslandSelection(unittest.TestCase):
    def setUp(self):
        # Setup sample graph
        # Top branch:    top1 (normal) -> top2 (elite) -> boss
        # Mid branch:    mid1 (rest)   -> mid2 (event) -> boss
        # Bot branch:    bot1 (event)  -> bot2 (normal) -> boss
        self.nodes_map = {
            "top1": ChaosNode("top1", ChaosNodeType.NORMAL),
            "top2": ChaosNode("top2", ChaosNodeType.ELITE),
            "mid1": ChaosNode("mid1", ChaosNodeType.REST),
            "mid2": ChaosNode("mid2", ChaosNodeType.EVENT),
            "bot1": ChaosNode("bot1", ChaosNodeType.EVENT),
            "bot2": ChaosNode("bot2", ChaosNodeType.NORMAL),
            "boss": ChaosNode("boss", ChaosNodeType.BOSS),
        }
        self.adj_list = {
            "top1": ["top2"],
            "top2": ["boss"],
            "mid1": ["mid2"],
            "mid2": ["boss"],
            "bot1": ["bot2"],
            "bot2": ["boss"],
        }
        self.island_roots = {
            IslandChoice.TOP: "top1",
            IslandChoice.MIDDLE: "mid1",
            IslandChoice.BOTTOM: "bot1",
        }
        self.boss_ids = {"boss"}

    def test_high_hp_selects_elite_path(self):
        # HP 80% >= 60%
        # Top: 1*Normal + 3*Elite = 4
        # Mid: -2*Rest + 0 = -2
        # Bot: 1*Normal + 0 = 1
        best_island, evals = select_best_island(
            self.island_roots, self.adj_list, self.nodes_map, self.boss_ids, hp_percent=0.80
        )
        self.assertEqual(best_island, IslandChoice.TOP)
        self.assertEqual(evals[IslandChoice.TOP].best_score, 4.0)

    def test_low_hp_rule_a_rejects_top_and_picks_mid(self):
        # HP 45% < 60%
        # Top has elite but no rest -> REJECTED by Rule A
        # Mid: 5*Rest + 2*Event = 7
        # Bot: 2*Event = 2
        best_island, evals = select_best_island(
            self.island_roots, self.adj_list, self.nodes_map, self.boss_ids, hp_percent=0.45
        )
        self.assertFalse(evals[IslandChoice.TOP].is_available)
        self.assertEqual(best_island, IslandChoice.MIDDLE)
        self.assertEqual(evals[IslandChoice.MIDDLE].best_score, 7.0)

    def test_tie_breaking_picks_shorter_path(self):
        # Path A (short):  mid1 (rest: 5) -> boss (total length 2)
        # Path B (long):   bot1 (rest: 5) -> bot2 (normal: 0) -> boss (total length 3)
        nodes = {
            "m1": ChaosNode("m1", ChaosNodeType.REST),
            "b1": ChaosNode("b1", ChaosNodeType.REST),
            "b2": ChaosNode("b2", ChaosNodeType.NORMAL),
            "boss": ChaosNode("boss", ChaosNodeType.BOSS),
        }
        adj = {
            "m1": ["boss"],
            "b1": ["b2"],
            "b2": ["boss"],
        }
        roots = {
            IslandChoice.MIDDLE: "m1",
            IslandChoice.BOTTOM: "b1",
        }
        best_island, evals = select_best_island(
            roots, adj, nodes, {"boss"}, hp_percent=0.50
        )
        # Both have score 5.0, but MIDDLE has length 2 vs BOTTOM length 3
        self.assertEqual(evals[IslandChoice.MIDDLE].best_score, 5.0)
        self.assertEqual(evals[IslandChoice.BOTTOM].best_score, 5.0)
        self.assertEqual(best_island, IslandChoice.MIDDLE)

    def test_single_available_island(self):
        # Only MIDDLE island exists (single narrow path)
        roots = {IslandChoice.MIDDLE: "mid1"}
        best_island, evals = select_best_island(
            roots, self.adj_list, self.nodes_map, self.boss_ids, hp_percent=0.70
        )
        self.assertEqual(best_island, IslandChoice.MIDDLE)

    def test_all_branches_invalid_returns_none(self):
        # Both paths have elite without rest and HP < 60%
        nodes = {
            "t1": ChaosNode("t1", ChaosNodeType.ELITE),
            "b1": ChaosNode("b1", ChaosNodeType.ELITE),
            "boss": ChaosNode("boss", ChaosNodeType.BOSS),
        }
        adj = {"t1": ["boss"], "b1": ["boss"]}
        roots = {IslandChoice.TOP: "t1", IslandChoice.BOTTOM: "b1"}
        best_island, evals = select_best_island(
            roots, adj, nodes, {"boss"}, hp_percent=0.30
        )
        self.assertIsNone(best_island)

    def test_unknown_node_invalidates_path(self):
        nodes = {
            "t1": ChaosNode("t1", ChaosNodeType.NORMAL),
            "t2": ChaosNode("t2", ChaosNodeType.UNKNOWN),
            "boss": ChaosNode("boss", ChaosNodeType.BOSS),
        }
        adj = {"t1": ["t2"], "t2": ["boss"]}
        roots = {IslandChoice.TOP: "t1"}
        best_island, evals = select_best_island(
            roots, adj, nodes, {"boss"}, hp_percent=0.80
        )
        self.assertIsNone(best_island)


if __name__ == "__main__":
    unittest.main()
