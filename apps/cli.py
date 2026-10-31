"""
CLI Application and Simulation runner for Chaos Zero Nightmare Bot.
"""
import os
import sys
import time
import argparse

src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from czn_bot.states import Mode
from czn_bot.device.adb import ADBClient
from czn_bot.device.mock import MockADBClient
from czn_bot.vision.detector import ScreenDetector
from czn_bot.runner import BotRunner


def run_cli(args):
    print("=== Chaos Zero Nightmare Bot (CLI Mode) ===")
    adb = ADBClient(host=args.host, port=args.port)
    print(f"Connecting to {args.host}:{args.port}...")
    if not adb.connect() and not adb.is_connected():
        print(f"Error: Unable to connect to ADB at {args.host}:{args.port}")
        sys.exit(1)
    print("ADB Connected!")
    ok_res, size, res_msg = adb.check_resolution()
    if not ok_res and size is not None:
        print(f"[!] CẢNH BÁO: {res_msg}!")
        print("[!] Bot được thiết kế tối ưu trên 1600x900. Vui lòng chỉnh trong BlueStacks Display Settings.")
    elif size is not None:
        print(f"[*] Độ phân giải màn hình: {size[0]}x{size[1]} (Chuẩn)")

    detector = ScreenDetector()
    runner = BotRunner(adb_client=adb, detector=detector)
    if args.mode == "chaos":
        runner.mode = Mode.CHAOS
    elif args.mode == "progress":
        runner.mode = Mode.PROGRESS
    elif args.mode == "story":
        runner.mode = Mode.STORY
    else:
        runner.mode = Mode.REPLAY

    runner.loop_delay = args.delay
    runner.max_retries = args.max_retries
    runner.auto_start_match = args.auto_start
    runner.chaos_strategy = args.strategy
    runner.enable_recovery = args.recovery

    print(f"[*] Chế độ: {runner.mode.value} | Chiến thuật: {args.strategy}")
    if args.recovery:
        print("[*] Tự động phục hồi khi gặp màn hình lạ (Recovery): BẬT")

    runner.on_log = lambda msg: print(f"[*] {msg}")
    runner.start()

    try:
        while runner.is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping bot...")
        runner.stop("User interrupted (Ctrl+C)")


def run_simulation(args):
    print("=== Chaos Zero Nightmare Bot (Offline Simulation Mode) ===")
    mock_adb = MockADBClient(args.simulate)
    print(f"Loaded {len(mock_adb.frames)} frame(s) from: {args.simulate}")

    detector = ScreenDetector()
    runner = BotRunner(adb_client=mock_adb, detector=detector)
    if args.mode == "chaos":
        runner.mode = Mode.CHAOS
    elif args.mode == "progress":
        runner.mode = Mode.PROGRESS
    elif args.mode == "story":
        runner.mode = Mode.STORY
    else:
        runner.mode = Mode.REPLAY

    runner.loop_delay = 0.05
    runner.max_retries = args.max_retries
    runner.auto_start_match = args.auto_start
    runner.chaos_strategy = args.strategy
    runner.enable_recovery = args.recovery
    runner.on_log = lambda msg: print(f"[*] {msg}")

    print("Starting simulation runner...")
    runner.start()

    start_time = time.time()
    try:
        while runner.is_running and (time.time() - start_time < 20):
            time.sleep(0.1)
            if mock_adb.current_idx >= len(mock_adb.frames) - 1 and mock_adb.step_count > 0:
                time.sleep(0.3)
                runner.stop("Kịch bản giả lập đã hoàn thành")
                break
    except KeyboardInterrupt:
        runner.stop("Dừng giả lập (Ctrl+C)")

    print(f"\nSimulation finished! Total taps: {len(mock_adb.tap_history)}")
    print(f"Annotated tap images saved to: {mock_adb.output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Chaos Zero Nightmare Bot CLI")
    parser.add_argument("--cli", action="store_true", default=True, help="Run in terminal CLI mode")
    parser.add_argument("--simulate", type=str, default=None, metavar="PATH",
                        help="Run offline simulation from a folder or screenshot")
    parser.add_argument("--host", default="127.0.0.1", help="ADB host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5555, help="ADB port (default: 5555)")
    parser.add_argument("--mode", choices=["replay", "progress", "chaos", "story"], default="replay")
    parser.add_argument("--delay", type=float, default=1.5, help="Loop delay in seconds")
    parser.add_argument("--max-retries", type=int, default=None, help="Maximum number of retries before stopping")
    parser.add_argument("--auto-start", action="store_true", help="Auto tap Enter on pre-match screens")
    parser.add_argument("--strategy", choices=["safe", "balanced", "aggressive"], default="balanced")
    parser.add_argument("--recovery", action="store_true", help="Bật recovery tự động khi gặp UNKNOWN")

    args = parser.parse_args()

    if args.simulate:
        run_simulation(args)
    else:
        run_cli(args)


if __name__ == "__main__":
    main()
