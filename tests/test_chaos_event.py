"""
Unit tests for Chaos Event Detection & Autonomous Event Choice Selection
based on event_rules.json and Season card templates.
"""
import os
import unittest
import numpy as np
import cv2

from czn_bot.states import State, Mode
from czn_bot.vision.detector import ScreenDetector
from czn_bot.chaos.rules import ChaosRuleManager
from czn_bot.chaos.decisions import ChaosVision, ResourceInfo
from czn_bot.chaos.ai_brain import ChaosAIBrain
from czn_bot.chaos.state_machine import ChaosStateMachine, ChaosState
from czn_bot.flows.chaos import ChaosFlow
from czn_bot.flows.base import ActionType


class TestChaosEvent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img_path = os.path.join(os.path.dirname(__file__), "fixtures", "labeled", "CHAOS_EVENT", "event_wager_poacher.jpg")
        if os.path.exists(cls.img_path):
            raw = cv2.imread(cls.img_path)
            cls.screen = cv2.resize(raw, (1600, 900))
        else:
            cls.screen = None

        cls.rule_manager = ChaosRuleManager()
        cls.vision = ChaosVision(rule_manager=cls.rule_manager)
        cls.brain = ChaosAIBrain(rule_manager=cls.rule_manager)
        cls.detector = ScreenDetector()

    def test_state_enum_has_chaos_event(self):
        self.assertTrue(hasattr(State, "CHAOS_EVENT"))
        self.assertEqual(State.CHAOS_EVENT.value, "CHAOS_EVENT")

    def test_event_detection_on_screen(self):
        if self.screen is None:
            self.skipTest("Screen image not available")
        state, details = self.detector.detect(self.screen)
        self.assertEqual(state, State.CHAOS_EVENT)
        self.assertIn("score", details)
        self.assertGreaterEqual(details.get("score", 0), 0.75)

    def test_state_machine_identifies_event(self):
        if self.screen is None:
            self.skipTest("Screen image not available")
        sm = ChaosStateMachine(detector=self.detector, vision=self.vision, brain=self.brain)
        st, details = sm.identify_state(self.screen)
        self.assertEqual(st, ChaosState.STATE_EVENT)

    def test_extract_event_choices_matches_event_rules(self):
        if self.screen is None:
            self.skipTest("Screen image not available")
        choices = self.vision.extract_event_choices(self.screen)
        self.assertEqual(len(choices), 3)

        # Verify choices matched event_rules.json
        matched_events = [c.matched_event_name for c in choices]
        self.assertTrue(any("Smuggled Goods Wager" in name for name in matched_events))

        # Check choice contents
        c0, c1, c2 = choices[0], choices[1], choices[2]
        self.assertIn("ask", c0.text.lower())
        self.assertIn("bet", c1.text.lower())
        self.assertIn("warn", c2.text.lower())

        # Choice 3 has priority 6 (Gain 80 credits) vs Priority 5
        self.assertEqual(c2.priority_score, 6)

    def test_brain_decision_picks_highest_priority(self):
        if self.screen is None:
            self.skipTest("Screen image not available")
        choices = self.vision.extract_event_choices(self.screen)
        res = ResourceInfo(hp_percent=0.94, is_low_hp=False, credits=213)
        decision = self.brain.decide_event(choices, res)

        self.assertEqual(decision.get("target_index"), 2)
        self.assertIn("Credits", decision.get("reason", ""))

    def test_chaos_flow_handles_chaos_event(self):
        if self.screen is None:
            self.skipTest("Screen image not available")
        flow = ChaosFlow(
            rule_manager=self.rule_manager,
            ai_brain=self.brain,
            vision=self.vision
        )
        action = flow.handle(State.CHAOS_EVENT, {}, self.screen)

        self.assertEqual(action.type, ActionType.TAP)
        # Should tap Choice 3 (x ~ 1215, y ~ 765)
        self.assertAlmostEqual(action.x, 1215, delta=50)
        self.assertAlmostEqual(action.y, 765, delta=50)
        extra_acts = action.extra.get("extra_actions", [])
        self.assertTrue(len(extra_acts) >= 1)
        # Verify 2nd tap is to the exact same choice coord (double tap selection)
        self.assertEqual(extra_acts[0], ("tap", (action.x, action.y)))

    def test_season_card_templates_loaded_and_matched(self):
        # Verify season card templates can be matched by ChaosVision
        season_dir = os.path.join("data", "templates", "Season")
        self.assertTrue(os.path.isdir(season_dir))
        season_files = [f for f in os.listdir(season_dir) if f.endswith(".png")]
        self.assertGreater(len(season_files), 10)

        # Load one template directly to test match_card_by_template
        test_file = season_files[0]
        test_path = os.path.join(season_dir, test_file)
        test_img = cv2.imread(test_path)
        self.assertIsNotNone(test_img)

        # Match against loaded templates
        matched = self.vision.match_card_by_template(test_img, threshold=0.60)
        self.assertIsNotNone(matched)
        self.assertEqual(matched.get("character"), "Season")


if __name__ == "__main__":
    unittest.main()
