import sys
import subprocess
import shutil

file_path = sys.argv[1] if len(sys.argv) > 1 else ""
if file_path.endswith(".py"):
    # Try ruff first, fallback to black
    if shutil.which("ruff"):
        subprocess.run(["ruff", "format", file_path], capture_output=True)
    elif shutil.which("black"):
        subprocess.run(["black", file_path], capture_output=True)
