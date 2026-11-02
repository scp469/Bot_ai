---
name: dev-setup
description: One-command environment setup for the Chaos Zero Nightmare bot. Installs Python deps, checks module imports, validates template integrity, verifies the ADB connection, and runs an OFFLINE smoke test.
disable-model-invocation: false
---

# Dev Setup

Onboard a contributor or configure environment for the Chaos Zero Nightmare bot project.

## Prerequisites

- Windows 10/11 (with RapidOCR or WinRT)
- Python 3.10+ in PATH
- Android emulator (BlueStacks / LDPlayer / MuMu) with ADB enabled

## Steps

### 1. Install dependencies

```bash
pip install -r requirements.txt
python -c "import cv2, PIL, numpy, pytest; print('deps OK')"
```

### 2. Verify modules import cleanly

```bash
python -c "
import sys; sys.path.insert(0, 'src')
from czn_bot.constants import TEMPLATES
from czn_bot.vision.detector import ScreenDetector
from czn_bot.chaos2 import ChaosLoop, ChaosClassifier, TapGuard
print('Core modules import cleanly!')
"
```

### 3. Verify ADB and 1600x900 resolution (Live runs)

```bash
adb connect localhost:5555
adb devices
```
Ensure emulator display resolution is configured to **1600x900** (DPI 240).

### 4. Template integrity check

```bash
python -c "
import sys; sys.path.insert(0, 'src')
from pathlib import Path
from czn_bot.constants import TEMPLATES, DATA_TEMPLATES_DIR
root = Path(DATA_TEMPLATES_DIR)
missing = [k for k, v in TEMPLATES.items() if not (root / v).exists()]
if missing:
    print('Missing templates:', missing)
else:
    print(f'All {len(TEMPLATES)} templates verified!')
"
```

### 5. Offline smoke test (Safe)

Run the Chaos2 test harness:
```bash
python -m pytest tests/test_chaos2_harness.py -v -s
```
Ensure 100% tests pass.
