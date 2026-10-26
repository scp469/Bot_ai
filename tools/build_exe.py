"""
Automated PyInstaller Build Script for Chaos Zero Nightmare AI Bot.
Packages main.py, GUI, OpenCV, CustomTkinter, Google GenAI SDK, and template assets
into a single standalone executable.
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
        import PyInstaller
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

    templates_dir = os.path.join(BASE_DIR, "templates")
    dist_dir = os.path.join(BASE_DIR, "dist")
    build_dir = os.path.join(BASE_DIR, "build")

    # Command line arguments for pyinstaller
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=ChaosZeroNightmare_AIBot",
        "--noconsole",
        "--onefile",
        f"--add-data={templates_dir};templates",
        f"--add-data={os.path.join(BASE_DIR, 'card_rules.json')};.",
        f"--add-data={os.path.join(BASE_DIR, 'event_rules.json')};.",
    ]

    if ctk_dir:
        cmd.append(f"--add-data={ctk_dir};customtkinter")

    # Hidden imports
    hidden_imports = [
        "customtkinter",
        "PIL",
        "PIL.Image",
        "cv2",
        "numpy",
        "google.genai",
        "google.genai.types",
        "requests",
        "urllib3",
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
        print("Người dùng sẽ tự điền API Key cá nhân trong giao diện để sử dụng.")
        print("=" * 60)
        return True
    else:
        print(f"[❌] Quá trình biên dịch thất bại với mã lỗi: {res.returncode}")
        return False


if __name__ == "__main__":
    build_executable()
