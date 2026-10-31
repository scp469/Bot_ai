"""
Unit tests for Chaos Strategy Profiles (Safe, Balanced, Aggressive).
"""
import unittest

from czn_bot.chaos.pathfinder import (
    ChaosNode,
    ChaosNodeType,
    IslandChoice,
    select_best_island,
    StrategyMode,
    get_strategy_profile,
    PROFILE_SAFE,
    PROFILE_BALANCED,
    PROFILE_AGGRESSIVE,
)


class TestStrategyProfile(unittest.TestCase):
    def setUp(self):
        self.node_normal = ChaosNode("n1", ChaosNodeType.NORMAL)
        self.node_elite = ChaosNode("e1", ChaosNodeType.ELITE)
        self.node_rest = ChaosNode("r1", ChaosNodeType.REST)
        self.node_event = ChaosNode("v1", ChaosNodeType.EVENT)
        self.node_boss = ChaosNode("b1", ChaosNodeType.BOSS)

    def test_get_strategy_profile(self):
        self.assertEqual(get_strategy_profile("safe").mode, StrategyMode.SAFE)
        self.assertEqual(get_strategy_profile("an toàn").mode, StrategyMode.SAFE)
        self.assertEqual(get_strategy_profile("aggressive").mode, StrategyMode.AGGRESSIVE)
        self.assertEqual(get_strategy_profile("tấn công").mode, StrategyMode.AGGRESSIVE)
        self.assertEqual(get_strategy_profile("balanced").mode, StrategyMode.BALANCED)
        self.assertEqual(get_strategy_profile(None).mode, StrategyMode.BALANCED)

    def test_balanced_profile_scoring_and_filtering(self):
        path = [self.node_elite, self.node_normal, self.node_boss]

        # At high HP (80%): Elite is favored
        score_high = PROFILE_BALANCED.calculate_path_score(path, 0.80)
        self.assertAlmostEqual(score_high, 4.0)  # 3*1 + 1*1 = 4.0

        # At low HP (50%): Rule A rejects elite without prior rest
        is_valid, reason = PROFILE_BALANCED.filter_path(path, 0.50)
        self.assertFalse(is_valid)
        self.assertIn("Tinh anh", reason)

    def test_safe_profile_strictly_avoids_elite_on_low_hp(self):
        # Even with rest before elite, Safe mode at low HP (< 70%) strictly rejects any Elite
        safe_path_with_rest_and_elite = [self.node_rest, self.node_elite, self.node_boss]
        is_valid, reason = PROFILE_SAFE.filter_path(safe_path_with_rest_and_elite, 0.65)
        self.assertFalse(is_valid)
        self.assertIn("An Toàn", reason)

        # Path with rest and event only is highly rewarded
        safe_clean_path = [self.node_rest, self.node_event, self.node_boss]
        score = PROFILE_SAFE.calculate_path_score(safe_clean_path, 0.65)
        self.assertAlmostEqual(score, 12.0)  # 8*1 + 4*1 = 12.0

    def test_aggressive_profile_tolerates_elite_at_moderate_hp(self):
        path = [self.node_elite, self.node_boss]
        # At 50% HP (above aggressive 40% threshold): elite is valid and heavily scored
        is_valid, _ = PROFILE_AGGRESSIVE.filter_path(path, 0.50)
        self.assertTrue(is_valid)
        score = PROFILE_AGGRESSIVE.calculate_path_score(path, 0.50)
        self.assertAlmostEqual(score, 5.0)

    def test_strategy_changes_island_selection(self):
        """Verify that Safe profile prefers Rest island while Aggressive prefers Elite island."""
        # Top branch: Normal -> Elite -> Boss
        # Bottom branch: Normal -> Rest -> Boss
        roots = {
            IslandChoice.TOP: "top_start",
            IslandChoice.BOTTOM: "bot_start",
        }
        nodes_map = {
            "top_start": ChaosNode("top_start", ChaosNodeType.NORMAL),
            "top_elite": ChaosNode("top_elite", ChaosNodeType.ELITE),
            "bot_start": ChaosNode("bot_start", ChaosNodeType.NORMAL),
            "bot_rest": ChaosNode("bot_rest", ChaosNodeType.REST),
            "boss": ChaosNode("boss", ChaosNodeType.BOSS),
        }
        adj = {
            "top_start": ["top_elite"],
            "top_elite": ["boss"],
            "bot_start": ["bot_rest"],
            "bot_rest": ["boss"],
        }
        boss_ids = {"boss"}

        # At 65% HP:
        # Aggressive considers 65% as high HP (> 40%) and favors Elite (Top)
        best_aggr, _ = select_best_island(roots, adj, nodes_map, boss_ids, 0.65, strategy="aggressive")
        self.assertEqual(best_aggr, IslandChoice.TOP)

        # Safe considers 65% as low HP (< 70%) and strictly rejects Elite, choosing Rest (Bottom)
        best_safe, _ = select_best_island(roots, adj, nodes_map, boss_ids, 0.65, strategy="safe")
        self.assertEqual(best_safe, IslandChoice.BOTTOM)


if __name__ == "__main__":
    unittest.main()
