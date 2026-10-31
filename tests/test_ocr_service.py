"""
Unit tests for centralized OcrService and Hybrid Verification engine.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

import cv2
import numpy as np

from czn_bot.vision import ocr as ocr_service
from czn_bot.vision.ocr import OcrService, get_ocr_service
from czn_bot.constants import TEMPLATES_DIR


class TestOcrService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = get_ocr_service()
        cls.fixture_dir = os.path.join(os.path.dirname(__file__), "fixtures")
        cls.templates_dir = TEMPLATES_DIR

    def test_ocr_availability(self):
        """Ensure OCR service is properly initialized and available."""
        self.assertTrue(self.service.is_available)
        self.assertTrue(ocr_service.is_ocr_available())

    def test_read_text_synthetic(self):
        """Verify text reading on synthetic rendered text."""
        img = np.zeros((60, 200, 3), dtype=np.uint8)
        img[:, :] = (255, 255, 255)
        cv2.putText(img, "CONFIRM", (15, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

        text = self.service.read_text(img)
        self.assertIn("CONFIRM", text.upper())

    def test_read_text_real_templates(self):
        """Verify reading text from actual game templates in templates/."""
        confirm_path = os.path.join(self.templates_dir, "confirm_button.png")
        if os.path.exists(confirm_path):
            img = cv2.imread(confirm_path)
            text = self.service.read_text(img)
            self.assertIn("confirm", text.lower())

        leave_path = os.path.join(self.templates_dir, "chaos_leave_button.png")
        if os.path.exists(leave_path):
            img = cv2.imread(leave_path)
            text = self.service.read_text(img)
            self.assertIn("leave", text.lower())

        skip_path = os.path.join(self.templates_dir, "chaos_safe_zone_skip.png")
        if os.path.exists(skip_path):
            img = cv2.imread(skip_path)
            text = self.service.read_text(img)
            self.assertIn("skip", text.lower())

    def test_find_text_full_screen(self):
        """Test finding center coordinates of a keyword across a 1600x900 screen."""
        screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        cv2.putText(screen, "CONFIRM", (1380, 830), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        cv2.putText(screen, "SKIP", (1250, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

        pt_confirm = self.service.find_text(screen, "confirm")
        self.assertIsNotNone(pt_confirm)
        # Should be near (1440, 820)
        self.assertTrue(1350 <= pt_confirm[0] <= 1550)
        self.assertTrue(790 <= pt_confirm[1] <= 860)

        pt_skip = self.service.find_text(screen, "skip", region=(1200, 10, 200, 100))
        self.assertIsNotNone(pt_skip)
        self.assertTrue(1220 <= pt_skip[0] <= 1350)
        self.assertTrue(20 <= pt_skip[1] <= 80)

        # Keyword not on screen
        pt_none = self.service.find_text(screen, "NONEXISTENT_KEYWORD")
        self.assertIsNone(pt_none)

    def test_verify_button_text_stage1(self):
        """Stage 1: Accurate hit when center point is directly on the button."""
        screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        cv2.putText(screen, "Confirm", (1380, 830), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

        is_valid = self.service.verify_button_text(screen, (1440, 825), "confirm")
        self.assertTrue(is_valid)

    def test_verify_button_text_stage2_expansion(self):
        """
        Stage 2: When initial crop box is slightly shifted/too tight,
        automatic expansion (+25px expand_pad) successfully catches the text.
        """
        screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        # Render "CONFIRM" around x: 1400..1540, y: 810..845
        cv2.putText(screen, "CONFIRM", (1400, 835), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

        # Bounding box is shifted right (1425, 805, 145, 50), cutting off 'C' -> Stage 1 reads '?NFIRM'
        # With expand_pad=35, it expands left to 1390 capturing 'C' -> Stage 2 succeeds with 'CONFIRM'
        box_shifted = (1425, 805, 145, 50)
        self.assertFalse(self.service.verify_button_text(screen, box_shifted, "confirm", expand_pad=0))
        self.assertTrue(self.service.verify_button_text(screen, box_shifted, "confirm", expand_pad=35))

    def test_verify_button_text_mismatch(self):
        """Ensure verification rejects wrong button text (negative verification)."""
        screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        cv2.putText(screen, "RETRY", (1380, 830), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

        # Expecting 'Confirm', but button is 'Retry'
        self.assertFalse(self.service.verify_button_text(screen, (1440, 825), "confirm"))

    def test_verify_button_text_multiple_keywords(self):
        """Accepts a list of synonym keywords."""
        screen = np.zeros((900, 1600, 3), dtype=np.uint8)
        cv2.putText(screen, "Leave", (1400, 830), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)

        self.assertTrue(
            self.service.verify_button_text(
                screen, (1440, 825), ["leave", "rời", "thoát"]
            )
        )

    def test_edge_cases_empty_or_none(self):
        """Ensure no crashes on invalid, empty, or None inputs."""
        self.assertEqual(self.service.read_text(None), "")
        self.assertEqual(self.service.read_text(np.zeros((0, 0, 3), dtype=np.uint8)), "")
        self.assertIsNone(self.service.find_text(None, "confirm"))
        self.assertFalse(self.service.verify_button_text(None, (100, 100), "confirm"))
        self.assertFalse(self.service.verify_button_text(np.zeros((10, 10, 3), dtype=np.uint8), (5, 5), "confirm"))

    def test_real_game_fixtures(self):
        """Test verification on real game screenshots in fixtures/."""
        # 1. chaos_reward_leave.png has Leave button at bottom right
        leave_fixture = os.path.join(self.fixture_dir, "chaos_reward_leave.png")
        if os.path.exists(leave_fixture):
            img = cv2.imread(leave_fixture)
            verified = self.service.verify_button_text(img, (1425, 830), ["leave", "confirm"])
            self.assertTrue(verified)

        # 2. chaos_continue.png has Continue button at bottom right
        cont_fixture = os.path.join(self.fixture_dir, "chaos_continue.png")
        if os.path.exists(cont_fixture):
            img = cv2.imread(cont_fixture)
            verified = self.service.verify_button_text(img, (1425, 830), ["continue", "next"])
            self.assertTrue(verified)

        # 3. chaos_safe_zone.png has Skip button at bottom right
        sz_fixture = os.path.join(self.fixture_dir, "chaos_safe_zone.png")
        if os.path.exists(sz_fixture):
            img = cv2.imread(sz_fixture)
            verified = self.service.verify_button_text(img, (1425, 830), ["skip", "bỏ qua"])
            self.assertTrue(verified)


if __name__ == "__main__":
    unittest.main()
