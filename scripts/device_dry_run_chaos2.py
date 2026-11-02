#!/usr/bin/env python3
"""
scripts/device_dry_run_chaos2.py - Script chạy thử nghiệm Perception & ChaosLoop (Dry-Run) trên thiết bị thật qua ADB.
Chế độ dry_run=True: CHỈ đọc màn hình, phân loại, trích xuất Facts và quyết định hành động, KHÔNG BAO GIỜ PHÁT TAP THẬT.

Cách sử dụng:
    python scripts/device_dry_run_chaos2.py [--serial <serial>] [--frames <n>] [--delay <sec>]

Ví dụ:
    python scripts/device_dry_run_chaos2.py --frames 5
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Thêm thư mục src vào sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import cv2
from czn_bot.device.adb import ADBClient
from czn_bot.vision.detector import ScreenDetector
from czn_bot.chaos2.classifier import ChaosClassifier
from czn_bot.chaos2.loop import ChaosLoop
from czn_bot.chaos2.perception.readers import (
    read_hp_facts,
    read_equipment_facts,
    read_map_facts,
    read_obtain_facts,
    read_event_facts,
    read_safe_zone_facts,
    read_fate_facts,
    read_duplicate_card_facts,
    read_settlement_facts,
    read_dialog_facts,
    read_epiphany_facts,
    read_remove_facts,
    read_copy_complete_facts,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Chaos2.DryRun")


def extract_screen_facts(state: str, screen, detector):
    """Trích xuất facts tương ứng với state hiện tại."""
    hp = read_hp_facts(screen)
    facts_obj = None
    if state == "CHAOS_EQUIPMENT":
        facts_obj = read_equipment_facts(screen, detector=detector)
    elif state == "CHAOS_MAP":
        facts_obj = read_map_facts(screen)
    elif state == "CHAOS_OBTAIN_REWARD":
        facts_obj = read_obtain_facts(screen)
    elif state == "CHAOS_EVENT":
        facts_obj = read_event_facts(screen)
    elif state == "CHAOS_SAFE_ZONE":
        facts_obj = read_safe_zone_facts(screen, detector=detector)
    elif state == "CHAOS_CHOOSE_FATE":
        facts_obj = read_fate_facts(screen)
    elif state == "CHAOS_SELECT_DUPLICATE_CARD":
        facts_obj = read_duplicate_card_facts(screen)
    elif state == "CHAOS_SETTLEMENT":
        facts_obj = read_settlement_facts(screen, detector=detector)
    elif state == "CHAOS_CHOOSE_EPIPHANY":
        facts_obj = read_epiphany_facts(screen)
    elif state == "CHAOS_REMOVE_CARD":
        facts_obj = read_remove_facts(screen)
    elif state == "CHAOS_COPY_COMPLETE":
        facts_obj = read_copy_complete_facts(screen)

    dialog = read_dialog_facts(screen)
    return hp, facts_obj, dialog


def main():
    parser = argparse.ArgumentParser(description="Chạy thử nghiệm Chaos2 Perception trên thiết bị thật qua ADB.")
    parser.add_argument("--serial", type=str, default=None, help="ADB device serial (mặc định chọn thiết bị đầu tiên)")
    parser.add_argument("--frames", type=int, default=10, help="Số frame chụp để đánh giá (mặc định 10)")
    parser.add_argument("--delay", type=float, default=1.0, help="Độ trễ giữa các frame tính theo giây (mặc định 1.0)")
    args = parser.parse_args()

    logger.info("Khởi tạo kết nối ADB...")
    try:
        adb = ADBClient()
        connected = adb.connect()
        if not connected and not adb.is_connected():
            logger.error(
                f"Không thể kết nối tới thiết bị ADB {adb.device}! Hãy đảm bảo đã bật USB Debugging hoặc giả lập và chạy: adb devices"
            )
            return 1
    except Exception as e:
        logger.error(f"Lỗi kết nối ADB: {e}")
        return 1

    logger.info("Tải tài nguyên nhận diện (ScreenDetector & ChaosClassifier)...")
    detector = ScreenDetector()
    classifier = ChaosClassifier(matcher=detector.match)
    loop = ChaosLoop(classifier=classifier, dry_run=True)

    logger.info(f"Bắt đầu vòng lặp Dry-Run ({args.frames} frames, delay={args.delay}s)...")
    logger.info("Chế độ DRY-RUN: Mọi hành động chỉ ghi log, KHÔNG phát bất kỳ tap thật nào.")

    for f_idx in range(1, args.frames + 1):
        logger.info(f"--- Frame {f_idx}/{args.frames} ---")
        screen = adb.screencap()
        if screen is None or screen.size == 0:
            logger.warning("Không chụp được màn hình thiết bị!")
            time.sleep(args.delay)
            continue

        res = classifier.classify(screen)
        logger.info(f"Phân loại: State={res.state} | Confidence={res.confidence:.2f} | Margin={res.margin:.2f}")

        hp, facts_obj, dialog = extract_screen_facts(res.state, screen, detector)
        if hp:
            logger.info(f"  [HP] {hp.current_hp}/{hp.max_hp} ({hp.hp_fraction*100:.0f}%) | Low HP={hp.is_low_hp}")
        else:
            logger.info("  [HP] None (màn hình không có thanh HUD HP)")

        if dialog.confirm_center:
            logger.info(f"  [Dialog Overlay] Phát hiện dialog '{dialog.dialog_type}' | Confirm: {dialog.confirm_center}")

        if facts_obj:
            logger.info(f"  [Facts] {facts_obj}")

        # Chạy bước quyết định của Loop (Dry-Run an toàn)
        action = loop.step(screen)
        logger.info(f"  [Quyết định Loop (Dry-Run)] Type={action.type} Target={action.target} Reason='{action.reason}'")

        if action.type == "stop":
            logger.warning(f"Vòng lặp yêu cầu DỪNG AN TOÀN: {action.reason}")
            break

        time.sleep(args.delay)

    logger.info("Hoàn tất phiên kiểm tra Dry-Run thiết bị thành công!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
