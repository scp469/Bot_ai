---
name: stall-to-regression-test
description: Convert a diagnosed capture from debug_captures/ into a permanent regression test fixture under tests/fixtures/states/ and a pytest test case in tests/test_chaos2_harness.py. Prevents recurring detector or flow regressions.
disable-model-invocation: false
---

# Stall to Regression Test (Chaos2)

Turn a diagnosed capture from `debug_captures/` into a permanent, deterministic regression test under `tests/`.

## Workflow

### 1. Select the Representative Capture
Screenshots are ~1.6MB each (1600x900). Only promote the single cleanest representative screenshot that demonstrates the issue.

### 2. Add to State Test Fixtures
Copy the image to `tests/fixtures/states/<descriptive_state_name>.png`.

Example command:
```bash
cp "debug_captures/unknown_stuck_CHAOS_EVENT_1793603177.png" "tests/fixtures/states/event_new_layout.png"
```

### 3. Add to Test Harness
Open `tests/test_chaos2_harness.py` and register the new fixture in `expected_states`:
```python
"event_new_layout.png": "CHAOS_EVENT",
```

### 4. Verify Accuracy & Zero Regressions
Run pytest harness:
```bash
python -m pytest tests/test_chaos2_harness.py -v -s
```
Ensure 100% green tests, high confidence, and clear margin.
