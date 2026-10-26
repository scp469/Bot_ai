"""
Main entry point for Chaos Zero Nightmare Bot.
Run with no arguments for GUI, or with --cli for headless terminal mode.
"""
import sys
import argparse

from config import Mode
from adb_client import ADBClient
from detector import ScreenDetector
from bot_engine import BotEngine


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
    engine = BotEngine(adb_client=adb, detector=detector)
    if args.mode == "chaos":
        engine.mode = Mode.CHAOS
    elif args.mode == "progress":
        engine.mode = Mode.PROGRESS
    elif args.mode == "story":
        engine.mode = Mode.STORY
    else:
        engine.mode = Mode.REPLAY
    engine.loop_delay = args.delay
    engine.max_retries = args.max_retries
    engine.auto_start_match = args.auto_start
    engine.chaos_strategy = args.strategy
    engine.enable_recovery = args.recovery

    print(f"[*] Chiến thuật Chaos: {args.strategy}")
    if args.recovery:
        print("[*] Recovery tự động: BẬT")

    engine.on_log = lambda msg: print(f"[*] {msg}")
    engine.start()

    try:
        while engine.is_running:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping bot...")
        engine.stop("User interrupted (Ctrl+C)")


def run_simulation(args):
    print("=== Chaos Zero Nightmare Bot (Offline Simulation Mode) ===")
    from mock_adb import MockADBClient
    mock_adb = MockADBClient(args.simulate)
    print(f"Loaded {len(mock_adb.frames)} frame(s) from: {args.simulate}")

    detector = ScreenDetector()
    engine = BotEngine(adb_client=mock_adb, detector=detector)
    if args.mode == "chaos":
        engine.mode = Mode.CHAOS
    elif args.mode == "progress":
        engine.mode = Mode.PROGRESS
    elif args.mode == "story":
        engine.mode = Mode.STORY
    else:
        engine.mode = Mode.REPLAY

    engine.loop_delay = 0.1  # Fast loop for simulation
    engine.max_retries = args.max_retries
    engine.auto_start_match = args.auto_start
    engine.chaos_strategy = args.strategy
    engine.enable_recovery = args.recovery
    engine.on_log = lambda msg: print(f"[*] {msg}")

    print("Starting simulation engine...")
    engine.start()

    import time
    start_time = time.time()
    try:
        while engine.is_running and (time.time() - start_time < 20):
            time.sleep(0.2)
            if mock_adb.current_idx >= len(mock_adb.frames) - 1 and mock_adb.step_count > 0:
                time.sleep(0.5)
                engine.stop("Kịch bản giả lập đã hoàn thành")
                break
    except KeyboardInterrupt:
        engine.stop("Dừng giả lập (Ctrl+C)")

    print(f"\nSimulation finished! Total taps: {len(mock_adb.tap_history)}")
    print(f"Annotated tap images saved to: {mock_adb.output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Chaos Zero Nightmare BlueStacks Bot")
    parser.add_argument("--cli", action="store_true", help="Run in terminal CLI mode without GUI")
    parser.add_argument("--simulate", type=str, default=None, metavar="PATH",
                        help="Run offline simulation from a folder of images or a single screenshot")
    parser.add_argument("--host", default="127.0.0.1", help="ADB host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5555, help="ADB port (default: 5555)")
    parser.add_argument("--mode", choices=["replay", "progress", "chaos", "story"], default="replay", help="Mode: replay, progress, chaos, or story")
    parser.add_argument("--delay", type=float, default=1.5, help="Loop delay in seconds")
    parser.add_argument("--max-retries", type=int, default=None, help="Maximum number of retries before stopping")
    parser.add_argument("--auto-start", action="store_true", help="Auto tap Enter on pre-match screens")
    parser.add_argument(
        "--strategy",
        choices=["safe", "balanced", "aggressive"],
        default="balanced",
        help="Chaos strategy: safe (ưu tiên sống), balanced (mặc định), aggressive (ưu tiên Elite)",
    )
    parser.add_argument(
        "--recovery",
        action="store_true",
        help="Bật recovery tự động khi gặp trạng thái UNKNOWN",
    )
    parser.add_argument(
        "--start",
        action="store_true",
        help="Tự động bắt đầu bot ngay khi mở GUI",
    )

    args = parser.parse_args()

    if args.simulate:
        run_simulation(args)
    elif args.cli:
        run_cli(args)
    else:
        from gui import main as run_gui
        run_gui(args)


if __name__ == "__main__":
    main()

