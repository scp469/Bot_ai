#!/usr/bin/env python3
"""
PostToolUse hook: chạy CHỈ các test liên quan đến file vừa được Edit/Write.

Đầu vào (thử lần lượt):
  1. JSON trên stdin có tool_input.file_path (hoặc tool_input.path / file_path)
  2. Đối số dòng lệnh (python run_related_tests.py <file>)
  3. Biến môi trường CLAUDE_FILE_PATHS / EDITED_FILE

Quy tắc thoát:
  0  = không có gì để chạy, hoặc test qua
  2  = test lỗi (in lỗi ra stderr để agent đọc được và sửa)
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TIMEOUT = 120

# module stem -> các file test cần chạy (tên không có đuôi .py)
RELATED = {
    # Chaos2 modules
    "action":             ["test_chaos2_harness"],
    "classifier":         ["test_chaos2_harness"],
    "config":             ["test_chaos2_harness"],
    "dryrun":             ["test_chaos2_harness"],
    "guard":              ["test_chaos2_harness"],
    "loop":               ["test_chaos2_harness"],
    "registry":           ["test_chaos2_harness"],
    "facts":              ["test_chaos2_harness"],
    "readers":            ["test_chaos2_harness"],
    # Vision & core infra
    "detector":           ["test_chaos2_harness", "test_chaos_detector"],
    "state_classifier":   ["test_phase_2_5_states", "test_chaos2_harness"],
    "scaler":             ["test_chaos2_harness"],
    "ocr":                ["test_chaos2_harness"],
    # Flows khác
    "story":              ["test_story_mode"],
    "replay":             ["test_bot_engine"],
    "progress":           ["test_bot_engine"],
    "runner":             ["test_bot_engine"],
}


def edited_path() -> str:
    if not sys.stdin.isatty():
        try:
            data = json.load(sys.stdin)
            ti = data.get("tool_input", data) if isinstance(data, dict) else {}
            for k in ("file_path", "path", "filePath"):
                if ti.get(k):
                    return str(ti[k])
        except Exception:
            pass
    if len(sys.argv) > 1:
        return sys.argv[1]
    return os.environ.get("EDITED_FILE") or os.environ.get("CLAUDE_FILE_PATHS", "").split(os.pathsep)[0]


def pick_tests(path: Path) -> list:
    if path.suffix != ".py":
        return []
    stem = path.stem
    tests_dir = ROOT / "tests"
    try:
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        return []
    if rel.parts[0] == "tests":
        names = [stem] if stem.startswith("test_") else []
    else:
        names = RELATED.get(stem, [f"test_{stem}"])
    return [n for n in names if (tests_dir / f"{n}.py").exists()]


def main() -> int:
    raw = edited_path()
    if not raw:
        return 0
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    test_names = pick_tests(path)
    if not test_names:
        return 0

    # Chạy qua pytest
    test_files = [f"tests/{n}.py" for n in test_names]
    cmd = [sys.executable, "-m", "pytest", *test_files, "-q"]
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f"[hook] Test quá {TIMEOUT}s: {' '.join(test_files)}", file=sys.stderr)
        return 2

    if proc.returncode == 0:
        print(f"[hook] OK: {', '.join(test_names)}")
        return 0
    tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-25:])
    print(f"[hook] TEST LỖI sau khi sửa {path.name}:\n{tail}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
