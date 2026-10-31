"""
Automated PyInstaller Build Script for Chaos Zero Nightmare Bot.
Packages main.py, GUI, OpenCV, CustomTkinter, and template assets
into a single standalone offline executable.
"""
import os
import sys
import subprocess
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_executable():
    print("=" * 60)
    print("🚀 CHAOS ZERO NIGHTMARE AI BOT — PYINSTALLER PACKAGER")
    print("=" * 60)

    try:
        import PyInstaller  # type: ignore
        print(f"[*] Found PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("[!] PyInstaller chưa được cài đặt.")
        print("[*] Đang tự động cài đặt pyinstaller qua pip...")
        res = subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"])
        if res.returncode != 0:
            print("[❌] Cài đặt PyInstaller thất bại. Vui lòng chạy lệnh: pip install pyinstaller")
            return False

    # Find customtkinter directory to include assets
    try:
        import customtkinter
        ctk_dir = os.path.dirname(customtkinter.__file__)
        print(f"[*] CustomTkinter path: {ctk_dir}")
    except ImportError:
        ctk_dir = ""

    data_templates_dir = os.path.join(BASE_DIR, "data", "templates")
    data_rules_dir = os.path.join(BASE_DIR, "data", "rules")
    dist_dir = os.path.join(BASE_DIR, "dist")
    build_dir = os.path.join(BASE_DIR, "build")

    # Command line arguments for pyinstaller
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=ChaosZeroNightmare_AIBot",
        "--noconsole",
        "--onefile",
        f"--add-data={data_templates_dir};data/templates",
        f"--add-data={data_rules_dir};data/rules",
    ]

    # Also support legacy flat templates if present
    legacy_templates = os.path.join(BASE_DIR, "templates")
    if os.path.exists(legacy_templates):
        cmd.append(f"--add-data={legacy_templates};templates")

    if ctk_dir:
        cmd.append(f"--add-data={ctk_dir};customtkinter")

    # Hidden imports
    hidden_imports = [
        "customtkinter",
        "PIL",
        "PIL.Image",
        "cv2",
        "numpy",
        "requests",
        "urllib3",
        "czn_bot",
        "czn_bot.settings",
        "czn_bot.constants",
        "czn_bot.coords",
        "czn_bot.states",
        "czn_bot.device.adb",
        "czn_bot.device.mock",
        "czn_bot.vision.templates",
        "czn_bot.vision.ocr",
        "czn_bot.vision.detector",
        "czn_bot.vision.hp_reader",
        "czn_bot.vision.map_reader",
        "czn_bot.chaos.pathfinder",
        "czn_bot.chaos.rules",
        "czn_bot.chaos.decisions",
        "czn_bot.chaos.ai_brain",
        "apps",
        "apps.cli",
        "apps.gui",
        "czn_bot.vision.state_classifier",
        "czn_bot.chaos.state_machine",
        "czn_bot.flows.base",
        "czn_bot.flows.replay",
        "czn_bot.flows.progress",
        "czn_bot.flows.story",
        "czn_bot.flows.chaos",
        "czn_bot.runner",
        "czn_bot.recovery",
        "czn_bot.stats",
        "czn_bot.notifier",
    ]
    for hi in hidden_imports:
        cmd.append(f"--hidden-import={hi}")

    main_script = os.path.join(BASE_DIR, "main.py")
    cmd.append(main_script)

    print("\n[*] Đang tiến hành biên dịch (.exe)... Quá trình có thể mất từ 1-3 phút...")
    print(f"[*] Command: {' '.join(cmd)}\n")

    res = subprocess.run(cmd, cwd=BASE_DIR)
    if res.returncode == 0:
        exe_path = os.path.join(dist_dir, "ChaosZeroNightmare_AIBot.exe")
        print("\n" + "=" * 60)
        print("✅ BIÊN DỊCH THÀNH CÔNG!")
        print("=" * 60)
        print(f"File thực thi: {exe_path}")
        print("Bạn có thể chia sẻ trực tiếp file .exe này cho người dùng khác.")
        print("Bot hoạt động 100% offline, không cần cấu hình API Key.")
        print("=" * 60)
        return True
    else:
        print(f"[❌] Quá trình biên dịch thất bại với mã lỗi: {res.returncode}")
        return False


if __name__ == "__main__":
    build_executable()
