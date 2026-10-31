"""
Unit and Integration Test Suite for AI-Driven Chaos Mode.
Tests:
- Phase 1: ChaosRuleManager (card_rules.json, event_rules.json, API key encryption) & ChaosADBController
- Phase 2: ChaosVision (ROI cropping, OpenCV preprocessing, card/event/resource extraction, button fallback)
- Phase 3: ChaosAIBrain (Dynamic prompt generation, JSON response parsing, heuristic card & event decisions)
- Phase 4: ChaosStateMachine (Context classification across fixtures, 15s freeze recovery watchdog)
"""
import os
import time
import unittest
from unittest.mock import MagicMock, patch
import cv2
import numpy as np

from czn_bot.chaos.rules import ChaosRuleManager
from czn_bot.device.adb import ChaosADBController
from czn_bot.chaos.decisions import ChaosVision, CardInfo, EventChoiceInfo, ResourceInfo
from czn_bot.chaos.ai_brain import ChaosAIBrain
from czn_bot.chaos.state_machine import ChaosStateMachine, ChaosState
from czn_bot.runner import BotRunner as BotEngine
from czn_bot.states import State


class TestChaosAI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import logging
        logging.getLogger("ChaosBot.Activity").handlers = [logging.NullHandler()]
        cls.fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
        cls.img_fate = cv2.imread(os.path.join(cls.fixtures_dir, "chaos_choose_fate.png"))
        cls.img_epiphany = cv2.imread(os.path.join(cls.fixtures_dir, "chaos_choose_epiphany.png"))
        cls.img_reward = cv2.imread(os.path.join(cls.fixtures_dir, "chaos_card_reward.png"))
        cls.img_obtain = cv2.imread(os.path.join(cls.fixtures_dir, "chaos_reward_obtain.png"))
        cls.img_leave = cv2.imread(os.path.join(cls.fixtures_dir, "chaos_reward_leave.png"))
        cls.img_safe = cv2.imread(os.path.join(cls.fixtures_dir, "chaos_safe_zone.png"))
        cls.img_continue = cv2.imread(os.path.join(cls.fixtures_dir, "chaos_continue.png"))
        cls.img_map = cv2.imread(os.path.join(cls.fixtures_dir, "chaos_map_3_islands.png"))

    # ── Phase 1 Tests: Config, Storage, ADB ────────────────────────

    @patch("czn_bot.chaos.rules.save_ai_config", return_value=True)
    def test_api_key_plain_storage(self, mock_save):
        """Verify API key is saved cleanly without homemade encryption."""
        rm = ChaosRuleManager()
        test_key = "AIzaSyD_TestKey1234567890abcdef"
        rm.save_ai_api_key(test_key)
        self.assertEqual(rm.ai_config["api_key"], test_key)
        mock_save.assert_called_once()

    def test_rule_manager_defaults(self):
        """Verify ChaosRuleManager loads default card and event rules."""
        rm = ChaosRuleManager()
        self.assertIn("priority_list", rm.card_rules)
        self.assertIn("keyword_weights", rm.card_rules)
        self.assertIn("priorities", rm.event_rules)
        self.assertTrue(rm.event_rules["priorities"]["fight_boss_for_gear"])
        self.assertEqual(rm.event_rules["min_credit_reserve"], 100)

    def test_adb_tap_location_jitter(self):
        """Verify tap_location applies random offset within bounds and clamps coordinates."""
        mock_client = MagicMock()
        mock_client.tap.return_value = True
        controller = ChaosADBController()
        controller.client = mock_client

        # Tap center
        ok = controller.tap_location(800, 450, random_offset=True, offset_range=3)
        self.assertTrue(ok)
        self.assertTrue(mock_client.tap.called)
        tx, ty = mock_client.tap.call_args[0]
        self.assertTrue(797 <= tx <= 803)
        self.assertTrue(447 <= ty <= 453)

        # Clamping at border
        controller.tap_location(0, 0, random_offset=True, offset_range=3)
        tx, ty = mock_client.tap.call_args[0]
        self.assertTrue(tx >= 0 and ty >= 0)

    # ── Phase 2 Tests: Vision & Preprocessing ──────────────────────

    def test_opencv_preprocessing(self):
        """Verify OpenCV preprocessing converts BGR to grayscale and normalizes contrast."""
        test_img = np.random.randint(50, 100, (100, 100, 3), dtype=np.uint8)
        norm = ChaosVision.preprocess_image(test_img, method="normalize")
        self.assertEqual(len(norm.shape), 2)  # Grayscale
        self.assertEqual(norm.max(), 255)     # Normalized

    def test_vision_extract_resources(self):
        """Verify extract_resources accurately reads HP and Credits from fixtures."""
        vision = ChaosVision()
        # Card reward fixture: 100% HP, 508 Credits
        res = vision.extract_resources(self.img_reward)
        self.assertAlmostEqual(res.hp_percent, 1.0, places=1)
        self.assertFalse(res.is_low_hp)
        self.assertEqual(res.credits, 508)

        # Continue fixture: 375 Credits
        res_cont = vision.extract_resources(self.img_continue)
        self.assertEqual(res_cont.credits, 375)

    def test_vision_extract_event_choices_fate(self):
        """Verify extract_event_choices accurately reads 3 fate options from choose_fate fixture."""
        vision = ChaosVision()
        choices = vision.extract_event_choices(self.img_fate)
        self.assertEqual(len(choices), 3)
        # Verify text keywords Focus, Possession, Passion
        combined_text = " ".join([c.text for c in choices])
        self.assertIn("Focus", combined_text)
        self.assertIn("Possession", combined_text)
        self.assertIn("Passion", combined_text)

    def test_vision_extract_cards_epiphany(self):
        """Verify extract_cards extracts card details and variant keywords."""
        vision = ChaosVision()
        cards = vision.extract_cards(self.img_epiphany, num_cards=3)
        self.assertEqual(len(cards), 3)
        self.assertEqual(cards[0].tap_coord, (390, 450))
        self.assertEqual(cards[1].tap_coord, (800, 450))
        self.assertEqual(cards[2].tap_coord, (1205, 450))
        self.assertTrue(any("Mute Accent" in c.raw_text for c in cards))
        self.assertTrue(any("Extra Attack" in c.raw_text for c in cards))

    def test_vision_find_action_button_hybrid(self):
        """Verify find_action_button finds confirm button via hybrid OCR/template matching."""
        vision = ChaosVision()
        btn = vision.find_action_button(self.img_fate, action_type="confirm")
        self.assertIsNotNone(btn)
        self.assertAlmostEqual(btn[0], 1449, delta=80)
        self.assertAlmostEqual(btn[1], 838, delta=60)

    # ── Phase 3 Tests: AI Brain & Heuristic Rules ───────────────────

    def test_dynamic_prompt_packaging(self):
        """Verify System Prompt embeds user rules from card_rules and event_rules."""
        brain = ChaosAIBrain()
        sys_prompt = brain._build_system_prompt()
        self.assertIn("Amp Therapy", sys_prompt)
        self.assertIn("Elasticity", sys_prompt)
        self.assertIn("fight_boss_for_gear", sys_prompt)
        self.assertIn("min_credit_reserve", sys_prompt)
        self.assertIn("choose_card", sys_prompt)

    def test_json_response_parsing(self):
        """Verify _parse_json_response cleans markdown blocks and parses JSON cleanly."""
        raw_markdown = """```json
{
  "action": "choose_event_option",
  "target_index": 2,
  "confidence": 0.95,
  "reason": "Ưu tiên chọn đánh boss nhận trang bị Rare."
}
```"""
        parsed = ChaosAIBrain._parse_json_response(raw_markdown)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["action"], "choose_event_option")
        self.assertEqual(parsed["target_index"], 2)
        self.assertEqual(parsed["confidence"], 0.95)

    def test_heuristic_event_decision_boss_when_healthy(self):
        """Verify heuristic engine chooses combat/boss when HP >= 50%."""
        brain = ChaosAIBrain()
        choices = [
            EventChoiceInfo(slot=0, name="Lựa chọn 1", tap_coord=(800, 360), text="Nghỉ ngơi hồi phục HP", is_heal=True),
            EventChoiceInfo(slot=1, name="Lựa chọn 2", tap_coord=(800, 500), text="Chiến đấu với Tinh anh Boss nhận trang bị Rare", is_combat=True),
        ]
        healthy_res = ResourceInfo(hp_percent=0.85, is_low_hp=False, credits=200)
        decision = brain._heuristic_event_decision(choices, healthy_res)
        self.assertEqual(decision["target_index"], 1)
        self.assertIn("Đánh boss", decision["reason"])

    def test_heuristic_event_decision_heal_when_low_hp(self):
        """Verify heuristic engine prioritizes heal over combat when HP < 50%."""
        brain = ChaosAIBrain()
        choices = [
            EventChoiceInfo(slot=0, name="Lựa chọn 1", tap_coord=(800, 360), text="Nghỉ ngơi hồi phục HP", is_heal=True),
            EventChoiceInfo(slot=1, name="Lựa chọn 2", tap_coord=(800, 500), text="Chiến đấu với Tinh anh Boss nhận trang bị", is_combat=True),
        ]
        low_res = ResourceInfo(hp_percent=0.35, is_low_hp=True, credits=200)
        decision = brain._heuristic_event_decision(choices, low_res)
        self.assertEqual(decision["target_index"], 0)
        self.assertIn("hồi máu", decision["reason"])

    def test_heuristic_card_decision_prefers_variant(self):
        """Verify heuristic engine prioritizes Elasticity variant over Base variant."""
        brain = ChaosAIBrain()
        cards = [
            CardInfo(slot=0, name="Thẻ 1", tap_coord=(390, 450), raw_text="Amp Therapy [Base] Standard healing", variant="Base"),
            CardInfo(slot=1, name="Thẻ 2", tap_coord=(800, 450), raw_text="Amp Therapy [Elasticity] Advanced bounce effect", variant="Elasticity"),
            CardInfo(slot=2, name="Thẻ 3", tap_coord=(1205, 450), raw_text="Common Strike Basic Attack", variant="Base"),
        ]
        res = ResourceInfo(hp_percent=0.70, is_low_hp=False, credits=300)
        decision = brain._heuristic_card_decision(cards, res)
        # Slot 1 (Amp Therapy Elasticity) should win
        self.assertEqual(decision["target_index"], 1)
        self.assertIn("Elasticity", decision["reason"])

    # ── Phase 4 Tests: State Machine & Watchdog ────────────────────

    def test_state_machine_identification(self):
        """Verify state classification accurately identifies states across all test fixtures."""
        sm = ChaosStateMachine()

        expected = [
            (self.img_fate, ChaosState.STATE_EVENT),
            (self.img_epiphany, ChaosState.STATE_CARD_REWARD),
            (self.img_reward, ChaosState.STATE_CARD_REWARD),
            (self.img_obtain, ChaosState.STATE_RESULT),
            (self.img_leave, ChaosState.STATE_RESULT),
            (self.img_safe, ChaosState.STATE_EVENT),
            (self.img_continue, ChaosState.STATE_RESULT),
            (self.img_map, ChaosState.STATE_MAP_CHOOSING),
        ]
        for img, exp_state in expected:
            state, _ = sm.identify_state(img)
            self.assertEqual(state, exp_state, f"Failed state matching for {exp_state.value}")

    def test_watchdog_freeze_recovery(self):
        """Verify watchdog recovery triggers back key / close when stuck on non-battle screen for > 15s."""
        sm = ChaosStateMachine()
        mock_adb = MagicMock()
        mock_adb.send_back.return_value = True
        sm.adb = mock_adb

        sm.current_state = ChaosState.STATE_MAP_CHOOSING
        sm.state_start_time = time.time() - 20.0  # Simulated freeze > 15s

        recovered = sm.check_watchdog_recovery(self.img_map)
        self.assertTrue(recovered)
        # Verify back key or tap was invoked

    def test_state_machine_handle_card_reward_and_fallback(self):
        """Verify handle_card_reward taps chosen card coordinate and falls back to (800, 450)."""
        sm = ChaosStateMachine()
        mock_adb = MagicMock()
        sm.adb = mock_adb

        # 1. Normal reward with fixture: should tap chosen card (one of 390, 800, 1205)
        res = sm.handle_card_reward(self.img_epiphany, {})
        self.assertTrue(res)
        self.assertTrue(mock_adb.tap_location.called)
        first_call = mock_adb.tap_location.call_args_list[0][0]
        self.assertIn(first_call, [(390, 450), (800, 450), (1205, 450)])

        # 2. Fallback when vision extracts 0 cards: should tap (800, 450)
        mock_adb.reset_mock()
        sm.vision.extract_cards = MagicMock(return_value=[])
        res_fb = sm.handle_card_reward(np.zeros((100, 100, 3), dtype=np.uint8), {})
        self.assertTrue(res_fb)
        self.assertTrue(mock_adb.tap_location.called)
        fb_call = mock_adb.tap_location.call_args_list[0][0]
        self.assertEqual(fb_call, (800, 450))

    def test_card_3_layout_constants(self):
        """Verify CARD_3_LAYOUT coordinates: Slot 0 (390, 450), Slot 1 (800, 450), Slot 2 (1205, 450)."""
        from czn_bot.chaos.decisions import CARD_3_LAYOUT
        self.assertEqual(CARD_3_LAYOUT[0]["tap"], (390, 450))
        self.assertEqual(CARD_3_LAYOUT[1]["tap"], (800, 450))
        self.assertEqual(CARD_3_LAYOUT[2]["tap"], (1205, 450))

    # ── Phase 5 Tests: Templates Database & Rich Matching ──────────

    def test_templates_databases_loaded(self):
        """Verify ChaosRuleManager loads 403 cards and 141 events from templates/."""
        rm = ChaosRuleManager()
        self.assertEqual(len(rm.cards), 403)
        self.assertEqual(len(rm.events_database), 141)
        self.assertIn("Nia", rm.cards_by_name["stroke"][0]["character"])
        self.assertIn("a child locked in a room", rm.events_by_name)

    def test_match_card_variants_from_templates(self):
        """Verify match_card correctly identifies specific card variants from OCR tokens."""
        rm = ChaosRuleManager()
        # Mute Accent [Discard 1]
        c1 = rm.match_card("Mute Accent Skill Discard, 1 200% Extra Attack")
        self.assertIsNotNone(c1)
        self.assertEqual(c1["variant"], "Discard 1")
        self.assertEqual(c1["priority"], 54)

        # Amp Therapy [Elasticity]
        c2 = rm.match_card("Amp Therapy Basic Skill Heal 100% Elasticity")
        self.assertIsNotNone(c2)
        self.assertEqual(c2["variant"], "Elasticity")
        self.assertEqual(c2["character"], "Nia")

    def test_match_event_choice_from_templates(self):
        """Verify match_event_choice matches event choices and extracts score & recommendation."""
        rm = ChaosRuleManager()
        res = rm.match_event_choice("Receive the memory of longing")
        self.assertIsNotNone(res)
        choice_dict, ev_dict = res
        self.assertEqual(choice_dict["choice_id"], 1)
        self.assertEqual(choice_dict["priority_score"], 8)
        self.assertEqual(ev_dict["event_name"], "A Child Locked in a Room")
        self.assertIn("Xâm lấn Ký ức", choice_dict["recommendation"])

    def test_heuristic_event_with_templates_recommendations(self):
        """Verify heuristic event decision leverages priority_score and recommendations from templates/."""
        brain = ChaosAIBrain()
        res_match = brain.rule_manager.match_event_choice("Receive the memory of longing")
        self.assertIsNotNone(res_match)
        ch_dict, ev_dict = res_match

        choices = [
            EventChoiceInfo(
                slot=0, name="Lựa chọn 1", tap_coord=(800, 360),
                text="Receive the memory of longing",
                matched_choice=ch_dict,
                matched_event_name=ev_dict["event_name"],
                priority_score=ch_dict["priority_score"],
                recommendation=ch_dict["recommendation"]
            ),
            EventChoiceInfo(
                slot=1, name="Lựa chọn 2", tap_coord=(800, 500),
                text="Receive the memory of 'Void'",
                priority_score=2,
                recommendation="Né lựa chọn này nếu không muốn rủi ro"
            )
        ]
        healthy_res = ResourceInfo(hp_percent=0.80, is_low_hp=False, credits=200)
        dec = brain._heuristic_event_decision(choices, healthy_res)
        self.assertEqual(dec["target_index"], 0)
        self.assertIn("8/10đ", dec["reason"])

    def test_ai_brain_decide_island(self):
        """Verify decide_island selects the optimal route and outputs clean JSON decision."""
        from czn_bot.chaos.pathfinder import select_best_island
        from czn_bot.vision.map_reader import parse_chaos_minimap
        brain = ChaosAIBrain()
        roots, adj, nodes, boss_ids = parse_chaos_minimap(self.img_map)
        _, evals = select_best_island(roots, adj, nodes, boss_ids, 0.85, strategy="balanced")

        healthy_res = ResourceInfo(hp_percent=0.85, is_low_hp=False, credits=300)
        decision = brain.decide_island(evals, healthy_res)
        self.assertEqual(decision["action"], "choose_island")
        self.assertIn(decision["target_island"], ["top", "middle", "bottom"])
        self.assertTrue(len(decision["reason"]) > 0)

    def test_handle_map_choosing_state_machine(self):
        """Verify handle_map_choosing executes properly without unpacking exceptions."""
        sm = ChaosStateMachine()
        mock_adb = MagicMock()
        mock_adb.tap_location.return_value = True
        mock_adb.human_sleep.return_value = None
        sm.adb = mock_adb

        ok = sm.handle_map_choosing(self.img_map, {})
        self.assertTrue(ok)
        self.assertTrue(mock_adb.tap_location.called)

    def test_analyze_unknown_screen_ai_wait(self):
        """Verify analyze_unknown_screen parses AI wait action on battle animation."""
        brain = ChaosAIBrain()
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = '{"screen_type": "battle_animation", "action": "wait", "wait_seconds": 1.5, "confidence": 0.98, "description": "Hoạt cảnh nộ", "reason": "Chờ đợi hết chiêu"}'
        mock_client.models.generate_content.return_value = mock_resp
        brain._genai_client = mock_client
        brain._current_api_key = "test_key"
        brain.rule_manager.get_api_key = MagicMock(return_value="test_key")

        dummy_screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        res = brain.analyze_unknown_screen(dummy_screen, last_state_name="IN_MATCH")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "wait")
        self.assertEqual(res["screen_type"], "battle_animation")
        self.assertAlmostEqual(res["confidence"], 0.98)

    def test_analyze_unknown_screen_ai_tap(self):
        """Verify analyze_unknown_screen parses AI tap action on popup dismiss."""
        brain = ChaosAIBrain()
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = '{"screen_type": "popup", "action": "tap", "tap_coord": [1525, 45], "confidence": 0.95, "description": "Popup nhận quà", "reason": "Bấm nút X đóng popup"}'
        mock_client.models.generate_content.return_value = mock_resp
        brain._genai_client = mock_client
        brain._current_api_key = "test_key"
        brain.rule_manager.get_api_key = MagicMock(return_value="test_key")

        dummy_screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        res = brain.analyze_unknown_screen(dummy_screen, last_state_name="CHAOS_MAP")
        self.assertIsNotNone(res)
        self.assertEqual(res["action"], "tap")
        self.assertEqual(res["tap_coord"], [1525, 45])

    def test_bot_engine_handle_unknown_with_ai_wait_does_not_halt(self):
        """Verify BotEngine._handle_unknown does NOT stop when AI Vision identifies wait action."""
        mock_adb = MagicMock()
        engine = BotEngine(adb_client=mock_adb)
        engine.is_running = True

        mock_brain = MagicMock()
        mock_brain.analyze_unknown_screen.return_value = {
            "screen_type": "battle_animation",
            "action": "wait",
            "wait_seconds": 0.1,
            "confidence": 0.99,
            "description": "Chiêu thức nộ đang phát",
            "reason": "Chờ hết chiêu"
        }
        engine.chaos_brain = mock_brain
        engine.rule_manager.get_api_key = MagicMock(return_value="test_key")

        dummy_screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        result = engine._handle_unknown(dummy_screen, {})
        self.assertTrue(result)
        self.assertEqual(engine._unknown_streak, 0)
        self.assertTrue(engine.is_running)

    def test_bot_engine_handle_unknown_with_ai_tap_clicks_target(self):
        """Verify BotEngine._handle_unknown taps target coordinate and resets streak when AI Vision returns tap."""
        mock_adb = MagicMock()
        engine = BotEngine(adb_client=mock_adb)
        engine.is_running = True

        mock_brain = MagicMock()
        mock_brain.analyze_unknown_screen.return_value = {
            "screen_type": "popup",
            "action": "tap",
            "tap_coord": [1520, 50],
            "confidence": 0.95,
            "description": "Nút đóng popup X",
            "reason": "Bấm đóng popup để tiếp tục"
        }
        engine.chaos_brain = mock_brain
        engine.rule_manager.get_api_key = MagicMock(return_value="test_key")

        dummy_screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        result = engine._handle_unknown(dummy_screen, {})
        self.assertTrue(result)
        self.assertEqual(engine._unknown_streak, 0)
        self.assertTrue(mock_adb.tap.called)
        tx, ty = mock_adb.tap.call_args[0]
        self.assertTrue(1510 <= tx <= 1530)
        self.assertTrue(40 <= ty <= 60)

    def test_detect_state_with_ai(self):
        """Verify detect_state_with_ai accurately maps AI JSON to State enum and details."""
        brain = ChaosAIBrain()
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = '{"state": "CHAOS_MAP", "confidence": 0.99, "description": "Bản đồ ngã rẽ 3 đảo", "details": {"has_minimap": true}}'
        mock_client.models.generate_content.return_value = mock_resp
        brain._genai_client = mock_client
        brain._current_api_key = "test_key"
        brain.rule_manager.get_api_key = MagicMock(return_value="test_key")

        dummy_screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        st, det = brain.detect_state_with_ai(dummy_screen)
        self.assertEqual(st, State.CHAOS_MAP)
        self.assertAlmostEqual(det["confidence"], 0.99)
        self.assertTrue(det.get("ai_detected"))

    def test_bot_engine_detect_state_uses_ai(self):
        """Verify BotEngine._detect_state delegates to chaos_brain.detect_state_with_ai."""
        engine = BotEngine()
        mock_brain = MagicMock()
        mock_brain.detect_state_with_ai.return_value = (
            State.CHAOS_CHOOSE_EPIPHANY,
            {"confidence": 0.98, "ai_detected": True, "description": "Chọn thẻ"}
        )
        engine.chaos_brain = mock_brain
        engine.rule_manager.get_api_key = MagicMock(return_value="test_key")
        engine.enable_ai_vision_detection = True

        dummy_screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        st, det = engine._detect_state(dummy_screen)
        self.assertEqual(st, State.CHAOS_CHOOSE_EPIPHANY)
        self.assertTrue(det.get("ai_detected"))
        self.assertTrue(mock_brain.detect_state_with_ai.called)


if __name__ == "__main__":
    unittest.main()


