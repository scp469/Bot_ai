---
name: diagnose-stall
description: Diagnose a stall, blocked tap, or wrongly detected screen in the Chaos Zero Nightmare bot from debug_captures/ and logs. Separates classifier anchor errors from guard violations, timing issues, and verification failures. Use when the bot gets stuck, stops safely, or reports UNKNOWN.
disable-model-invocation: false
---

# Diagnose Stall (Chaos2 & Bot Engine)

When the bot encounters an abnormal condition, it halts safely and dumps a screenshot into `debug_captures/` with prefixes:
- `unknown_stuck_<STATE>_<timestamp>.png` (unrecognized screen)
- `tap_blocked_by_guard_<timestamp>.png` (tap into forbidden zone)
- `action_verify_failed_<timestamp>.png` (action did not lead to expected_next)

## Step 1. Inspect the Saved Capture

Verify image resolution is exactly **1600x900**. Inspect the UI elements by eye to determine what screen it actually is.

## Step 2. Re-run Chaos2 Classifier on the Saved Frame

```bash
python -c "
import sys, cv2
from czn_bot.vision.detector import ScreenDetector
from czn_bot.chaos2.classifier import ChaosClassifier
from czn_bot.chaos2.registry import SCREEN_REGISTRY

det = ScreenDetector()
cls = ChaosClassifier(SCREEN_REGISTRY, matcher=det.match)
img = cv2.imread(sys.argv[1])
res = cls.classify(img)
print(f'State: {res.state} | Conf: {res.confidence:.2f} | Margin: {res.margin:.2f}')
print('Ranked:', res.ranked[:3])
" debug_captures/<filename>.png
```

## Step 3. Diagnose the Cause

| Category | Evidence | Where the fix goes |
|---|---|---|
| A. Negative Anchor false trigger | Correct state ruled out by a negative anchor | Adjust negative anchor threshold or ROI in `SCREEN_REGISTRY` |
| B. Positive Anchor low score | Missing a UI variant / layout | Add layout variant to `positive_layouts` in `SCREEN_REGISTRY` |
| C. Tap Guard Blocked | Tap landed in `forbidden_tap_zones` or out of bounds | Check handler coordinates or zone definitions in `guard.py` |
| D. Verification Timeout | Action executed but screen took > 5s to change | Adjust animation wait or `timeout_sec` in `ChaosAction` |
| E. Truly New Screen | Screen not yet registered in system | Follow `add-chaos2-screen` skill to register new screen |

## Step 4. Report & Lock with Regression Test

Report the category, the anchor scores, and the proposed fix. Once resolved, convert the capture into a permanent test fixture in `tests/fixtures/states/` and add test coverage.
