"""
Unit tests for Chaos Deck Engine: DeckPreset, DeckState, and DeckEvaluator.
"""
import os
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from czn_bot.constants import PROJECT_ROOT
from czn_bot.chaos.decisions import CardInfo
from czn_bot.chaos.deck_preset import CharacterPreset, PresetCardRule, load_preset
from czn_bot.chaos.deck_state import DeckState
from czn_bot.chaos.deck_evaluator import DeckEvaluator


class TestDeckPreset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rules_path = os.path.join(PROJECT_ROOT, "data", "rules", "card_rules.json")
        with open(rules_path, "r", encoding="utf-8") as f:
            cls.card_rules = json.load(f)

    def test_load_and_validate_rossweisse_preset(self):
        preset = load_preset("rossweisse", card_rules=self.card_rules)
        self.assertEqual(preset.character, "Rossweisse")
        self.assertGreaterEqual(len(preset.core_cards), 4)
        self.assertIn("rossweisse_sword_slash_base", preset.removal_priority)
        self.assertIn("rossweisse_flicker_blade_blink", [c.card_id for c in preset.core_cards])

    def test_load_and_validate_tiphera_preset(self):
        preset = load_preset("tiphera", card_rules=self.card_rules)
        self.assertEqual(preset.character, "Tiphera")
        self.assertGreaterEqual(len(preset.core_cards), 4)
        self.assertIn("tiphera_quantum_seed_cost0_create2_draw1", [c.card_id for c in preset.core_cards])

    def test_invalid_card_id_raises_value_error(self):
        bad_preset = CharacterPreset(
            character="Rossweisse",
            archetype="test",
            core_cards=[PresetCardRule(card_id="non_existent_fake_card_id")]
        )
        with self.assertRaises(ValueError) as ctx:
            bad_preset.validate(self.card_rules)
        self.assertIn("non_existent_fake_card_id", str(ctx.exception))

    def test_serialization_roundtrip(self):
        preset = CharacterPreset(
            character="TestHero",
            archetype="Burst",
            version="1.2.0",
            core_cards=[PresetCardRule(card_id="c1", min_copies=1, max_copies=2, priority=90)],
            epiphany_targets={"base_c1": "variant_c1"},
            removal_priority=["starter_c1"],
            max_deck_size=9
        )
        data = preset.to_dict()
        reconstructed = CharacterPreset.from_dict(data)
        self.assertEqual(preset.character, reconstructed.character)
        self.assertEqual(preset.max_deck_size, reconstructed.max_deck_size)
        self.assertEqual(len(reconstructed.core_cards), 1)
        self.assertEqual(reconstructed.core_cards[0].priority, 90)


class TestDeckState(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.state = DeckState(run_id="test_run_123", log_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_pick_and_count_cards(self):
        self.state.record_card_picked("Rossweisse", "c_blink", "Flicker Blade (Blink)")
        self.state.record_card_picked("Rossweisse", "c_blink", "Flicker Blade (Blink)")
        self.assertEqual(self.state.get_deck_size("Rossweisse"), 2)
        self.assertEqual(self.state.count_copies("Rossweisse", "c_blink"), 2)
        self.assertTrue(self.state.has_card("Rossweisse", "c_blink"))
        self.assertFalse(self.state.has_card("Rossweisse", "c_other"))

        # Verify JSONL log was written
        log_file = os.path.join(self.test_dir, "test_run_123.jsonl")
        self.assertTrue(os.path.isfile(log_file))
        with open(log_file, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["event"], "CARD_PICKED")
        self.assertEqual(lines[0]["details"]["card_name"], "Flicker Blade (Blink)")

    def test_remove_card(self):
        self.state.record_card_picked("Rossweisse", "c_slash", "Sword Slash")
        self.assertEqual(self.state.get_deck_size("Rossweisse"), 1)

        removed = self.state.record_card_removed("Rossweisse", "c_slash")
        self.assertTrue(removed)
        self.assertEqual(self.state.get_deck_size("Rossweisse"), 0)

    def test_upgrade_card(self):
        self.state.record_card_picked("Rossweisse", "c_flicker_base", "Flicker Blade")
        upgraded = self.state.record_card_upgraded(
            "Rossweisse", "c_flicker_base", "c_flicker_blink", "Blink"
        )
        self.assertTrue(upgraded)
        self.assertFalse(self.state.has_card("Rossweisse", "c_flicker_base"))
        self.assertTrue(self.state.has_card("Rossweisse", "c_flicker_blink"))


class TestDeckEvaluator(unittest.TestCase):
    def setUp(self):
        self.deck_state = DeckState()
        self.preset = CharacterPreset(
            character="Rossweisse",
            archetype="Flow",
            core_cards=[
                PresetCardRule(card_id="rossweisse_flicker_blade_blink", min_copies=1, max_copies=2, priority=95),
            ],
            epiphany_targets={
                "flicker_blade": "rossweisse_flicker_blade_blink"
            },
            removal_priority=["rossweisse_sword_slash_base"],
            max_deck_size=8
        )
        self.evaluator = DeckEvaluator(
            presets={"Rossweisse": self.preset},
            deck_state=self.deck_state
        )

    def test_evaluate_epiphany_prefers_target_variant(self):
        card1 = CardInfo(
            slot=0, name="Card 1", tap_coord=(390, 450),
            title="Flicker Blade", priority=60,
            matched_card={"id": "rossweisse_flicker_blade_blink"}
        )
        card2 = CardInfo(
            slot=1, name="Card 2", tap_coord=(800, 450),
            title="Standing Blade", priority=50,
            matched_card={"id": "rossweisse_standing_blade_base"}
        )

        best_idx, breakdowns = self.evaluator.evaluate_epiphany_choices([card1, card2], "Rossweisse")
        self.assertEqual(best_idx, 0)
        self.assertGreater(breakdowns[0].total_score, breakdowns[1].total_score)
        self.assertIn("Epiphany", "; ".join(breakdowns[0].reasons))

    def test_evaluate_epiphany_max_copies_penalty(self):
        # Already have 2 copies of blink in deck
        self.deck_state.record_card_picked("Rossweisse", "rossweisse_flicker_blade_blink", "Flicker Blade Blink")
        self.deck_state.record_card_picked("Rossweisse", "rossweisse_flicker_blade_blink", "Flicker Blade Blink")

        card_blink = CardInfo(
            slot=0, name="Card 1", tap_coord=(390, 450),
            title="Flicker Blade", priority=60,
            matched_card={"id": "rossweisse_flicker_blade_blink"}
        )
        _, breakdowns = self.evaluator.evaluate_epiphany_choices([card_blink], "Rossweisse")
        # Should have -60 marginal penalty
        self.assertEqual(breakdowns[0].v_marginal, -60.0)

    def test_evaluate_card_removal_identifies_starter_card(self):
        visible_cards = [
            "Flicker Blade Blink",
            "Sword Slash Basic Attack",
            "Blade of the Cycle"
        ]
        decision, slot, reason = self.evaluator.evaluate_card_removal(visible_cards, "Rossweisse")
        self.assertEqual(decision, "remove")
        self.assertEqual(slot, 1) # Sword Slash is at slot 1

    def test_evaluate_card_removal_skips_when_no_trash(self):
        visible_cards = [
            "Flicker Blade Blink",
            "Sword Resonance Activate All",
            "Blade of the Cycle Draw Discount"
        ]
        decision, slot, reason = self.evaluator.evaluate_card_removal(visible_cards, "Rossweisse")
        self.assertEqual(decision, "skip")
        self.assertIsNone(slot)

    def test_evaluate_card_reward_combatant_dynamic_selection(self):
        team = ["Rossweisse", "Tiphera", "Maribell"]
        # Case 1: Badge counts [7, 8, 8] -> slot 0 has 7 cards < max 8
        slot, reason = self.evaluator.evaluate_card_reward_combatant(
            card_title="Memory: Kaleidoscope",
            is_memory=True,
            team_characters=team,
            on_screen_counts=[7, 8, 8]
        )
        self.assertEqual(slot, 0)
        self.assertIn("Rossweisse", reason)

        # Case 2: Badge counts [8, 7, 8] -> slot 1 has 7 cards
        slot, reason = self.evaluator.evaluate_card_reward_combatant(
            card_title="Memory: Kaleidoscope",
            is_memory=True,
            team_characters=team,
            on_screen_counts=[8, 7, 8]
        )
        self.assertEqual(slot, 1)

        # Case 3: All at max size 8 -> choose lowest deck
        slot, reason = self.evaluator.evaluate_card_reward_combatant(
            card_title="Generic Card",
            is_memory=False,
            team_characters=team,
            on_screen_counts=[9, 7, 9]
        )
        self.assertEqual(slot, 1)


class TestRemoveCardGridAndVision(unittest.TestCase):
    def test_remove_card_grid_inside_bounds_and_pitch(self):
        from czn_bot.chaos.decisions import REMOVE_CARD_GRID
        self.assertEqual(len(REMOVE_CARD_GRID), 8)

        # 1. Verify tap coords are strictly inside respective ROIs
        for item in REMOVE_CARD_GRID:
            rx, ry, rw, rh = item["roi"]
            tx, ty = item["tap"]
            self.assertGreaterEqual(tx, rx, f"Tap x={tx} is left of ROI rx={rx} in slot {item['slot']}")
            self.assertLess(tx, rx + rw, f"Tap x={tx} is right of ROI rx+rw={rx+rw} in slot {item['slot']}")
            self.assertGreaterEqual(ty, ry, f"Tap y={ty} is above ROI ry={ry} in slot {item['slot']}")
            self.assertLess(ty, ry + rh, f"Tap y={ty} is below ROI ry+rh={ry+rh} in slot {item['slot']}")
            # All ROIs fit inside 1600x900
            self.assertGreaterEqual(rx, 0)
            self.assertLessEqual(rx + rw, 1600)
            self.assertGreaterEqual(ry, 0)
            self.assertLessEqual(ry + rh, 900)

        # 2. Verify horizontal pitch is ~265px across columns
        for row_start in [0, 4]:
            p1 = REMOVE_CARD_GRID[row_start + 1]["roi"][0] - REMOVE_CARD_GRID[row_start]["roi"][0]
            p2 = REMOVE_CARD_GRID[row_start + 2]["roi"][0] - REMOVE_CARD_GRID[row_start + 1]["roi"][0]
            p3 = REMOVE_CARD_GRID[row_start + 3]["roi"][0] - REMOVE_CARD_GRID[row_start + 2]["roi"][0]
            self.assertGreaterEqual(p1, 260)
            self.assertGreaterEqual(p2, 260)
            self.assertGreaterEqual(p3, 260)

    def test_extract_remove_cards_on_fixture(self):
        import cv2
        from czn_bot.chaos.decisions import ChaosVision
        fixture_path = os.path.join(PROJECT_ROOT, "tests", "fixtures", "chaos_remove_card.png")
        if not os.path.isfile(fixture_path):
            self.skipTest("chaos_remove_card.png fixture not found")

        img = cv2.imread(fixture_path)
        vision = ChaosVision()
        cards = vision.extract_remove_cards(img)

        # Should extract 7 visible cards without throwing
        self.assertGreaterEqual(len(cards), 4)
        slots = [c["slot"] for c in cards]
        # Slot 3 (Flicker Blade) must be captured now (previously missed)
        self.assertIn(3, slots)
        slot3_card = next(c for c in cards if c["slot"] == 3)
        self.assertIn("flicker", slot3_card["title"].lower())

    def test_extract_card_reward_combatant_counts_on_fixture(self):
        import cv2
        from czn_bot.chaos.decisions import ChaosVision
        fixture_path = os.path.join(PROJECT_ROOT, "tests", "fixtures", "chaos_card_reward.png")
        if not os.path.isfile(fixture_path):
            self.skipTest("chaos_card_reward.png fixture not found")

        img = cv2.imread(fixture_path)
        vision = ChaosVision()
        counts = vision.extract_card_reward_combatant_counts(img)
        self.assertEqual(len(counts), 3)
        self.assertEqual(counts, [7, 8, 8])


if __name__ == "__main__":
    unittest.main()

