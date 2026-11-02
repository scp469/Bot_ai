---
name: dev-setup
description: One-command environment setup for the Chaos Zero Nightmare bot. Installs Python deps, checks module imports, validates template integrity, optionally verifies the BlueStacks ADB connection, and runs an OFFLINE smoke test. Use when onboarding a new contributor or after a fresh checkout.
disable-model-invocation: false
---

# Dev Setup

Onboard a contributor to the Chaos Zero Nightmare bot project. Everything except step 3 works offline, without BlueStacks and without touching the game.

## Prerequisites

- Windows 11 (the OCR service uses WinRT)
- Python 3.10+ in PATH
- BlueStacks 5 with ADB enabled (only for live runs, step 3)

## Steps

### 1. Install dependencies

```bash
pip install -r requirements.txt
python -c "import cv2, PIL, numpy; print('deps OK')"
```

### 2. Verify modules import (catches Python-version problems)

```bash
python -c "import config, detector, chaos_pathfinder, bot_engine; print('imports OK')"
```

Known issues on Python 3.12: annotations use `typing` names that are never imported, which raises `NameError` at import time.

- `chaos_pathfinder.py` (`strategy: Optional[Any] = None`): add `Any` to its `from typing import ...` line.
- `bot_engine.py` (`expected_words: Optional[Union[str, List[str]]] = None`, near line 1085): the import on line 12 lacks `Union` and `List`; add them.

Because `bot_engine` is imported by most tests, the second one makes many tests fail on import. Fix the imports rather than changing the Python version, and re-run this step.

### 3. (Live runs only) Verify BlueStacks ADB and resolution

```bash
adb connect localhost:5555
adb devices
```

Expect a device with status `device`. The bot is hard-coded for **1600x900** (`SCREEN_WIDTH`, `SCREEN_HEIGHT` in `config.py`): BlueStacks Settings -> Display -> Resolution 1600x900, DPI 240. This applies to the **screenshots the bot captures**, not to the template files.

### 4. Check template integrity

Templates in `templates/` are small crops (for example 260x45), NOT full screens. Do not require 1600x900. Check instead that every file loads, every `TEMPLATES` entry points to an existing file, and nothing looks like an uncropped screenshot:

```bash
python -c "
import cv2
from pathlib import Path
from config import TEMPLATES, TEMPLATES_DIR
root = Path(TEMPLATES_DIR)
bad = 0
for key, name in TEMPLATES.items():
    p = root / name
    img = cv2.imread(str(p)) if p.exists() else None
    if img is None:
        print(f'MISSING/UNREADABLE  {key} -> {name}'); bad += 1; continue
    h, w = img.shape[:2]
    if (w, h) == (1600, 900) or w * h > 600 * 400:
        print(f'SUSPICIOUS (looks uncropped)  {key}: {w}x{h}'); bad += 1
referenced = set(TEMPLATES.values())
orphans = sorted(p.name for p in root.glob('*.png') if p.name not in referenced)
print(f'{len(TEMPLATES)} registered, {bad} problem(s), {len(orphans)} unreferenced png(s)')
for o in orphans: print('  unreferenced:', o)
"
```

Unreferenced PNGs are informational (they may be loaded by another module); missing or suspicious ones must be fixed.

### 5. Offline smoke test (safe)

Run the unit tests, then replay saved screenshots through the real pipeline with the mock ADB client:

```bash
python -m unittest discover tests
python main.py --simulate tests/fixtures/new --mode replay --max-retries 1
```

`--simulate PATH` accepts a folder of images or a single screenshot and never talks to the emulator. If the simulation keeps looping on static frames, stop it with Ctrl+C.

**Never** use a live `--mode replay` run as a smoke test: it drives the real game and can spend the in-game "Retry" currency.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `NameError: name 'Any'` on import | Missing `from typing import Any` in `chaos_pathfinder.py` | Add the import (step 2) |
| `adb: command not found` | ADB not in PATH | Add the BlueStacks ADB folder to PATH or use the full path |
| `adb connect` fails | ADB disabled in BlueStacks | Settings -> Advanced -> Enable ADB |
| Everything detects as UNKNOWN on live runs | Emulator not 1600x900 | Reset BlueStacks resolution (step 3) |
| Template reported MISSING | Entry in `TEMPLATES` without a file | Add the file or remove the entry |
| Bot taps the wrong place | Wrong `TAP_COORDS` | Review `TAP_COORDS` in `config.py` |
