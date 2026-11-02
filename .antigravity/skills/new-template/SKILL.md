---
name: new-template
description: Enforce template checklist for the Chaos Zero Nightmare bot project. Ensures all template images are correct resolution, cropped tightly, match-threshold sanity, and registered in constants.py and chaos2/registry.py.
disable-model-invocation: true
---

# New Template Checklist (Chaos2)

Enforce template standards for the Chaos Zero Nightmare bot project.

## Purpose

Templates in `data/templates/` are safety-critical. A bad template (wrong size, uncropped screenshot, or low threshold) can cause misclassification or false positive detections.

## Checklist

### 1. Template Dimensions & Resolution Source

Screenshots captured from the emulator must be exactly **1600×900** pixels.
However, **template images are small cropped regions** (e.g., 40×40 node icons, 260×45 button texts, title badges), **NOT full screenshots**.

**Run the template integrity check:**

```bash
python -c "
import cv2
from pathlib import Path
from czn_bot.constants import TEMPLATES, DATA_TEMPLATES_DIR
root = Path(DATA_TEMPLATES_DIR)
bad = 0
for key, name in TEMPLATES.items():
    p = root / name
    img = cv2.imread(str(p)) if p.exists() else None
    if img is None:
        print(f'MISSING/UNREADABLE  {key} -> {name}'); bad += 1; continue
    h, w = img.shape[:2]
    if (w, h) == (1600, 900) or w * h > 600 * 400:
        print(f'SUSPICIOUS (looks uncropped screenshot)  {key}: {w}x{h}'); bad += 1
print(f'Done: {len(TEMPLATES)} registered, {bad} problem(s)')
"
```

### 2. Match-Threshold Sanity

- Default match threshold in `czn_bot.constants` is **0.75 - 0.80**.
- Distinctive text / icons: threshold 0.75 is reliable.
- Generic button shapes (e.g. orange rectangles): must be combined with text OCR or negative anchors to avoid false positives.

### 3. Registration in System

When adding a new template:
1. Save the cropped PNG to `data/templates/<name>.png`.
2. Register the template key and filename in `TEMPLATES` in `src/czn_bot/constants.py`.
3. If used for state recognition in `chaos2`:
   - Add `AnchorDef` to `positive_layouts` or `negative_anchors` in `src/czn_bot/chaos2/registry.py`.
4. Run `pytest tests/test_chaos2_harness.py` to ensure high confidence and zero false matches across other fixtures.
