"""
eval_detector.py - Đo độ chính xác nhận diện state trên bộ ảnh đã gán nhãn.

Cấu trúc thư mục:
    tests/fixtures/labeled/<TEN_STATE>/*.png        (ảnh 1600x900, thư mục = nhãn đúng)

Chạy:
    python tools/eval_detector.py tests/fixtures/labeled
Kết quả: ma trận nhầm lẫn, danh sách ảnh nhận sai, ảnh có margin thấp (sắp sai).
Trả exit code 1 nếu có ảnh nhận sai -> dùng làm cổng CI.
"""
import sys
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple, Any

import cv2

# Đảm bảo import được czn_bot
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "src"))

from czn_bot.vision.detector import ScreenDetector
from czn_bot.vision.state_classifier import StateClassifier, DEFAULT_STATE_SPECS, calibrate_threshold

LOW_MARGIN = 0.20


def load_cases(root: Path):
    """Load all png/jpg test cases from state-labeled subdirectories."""
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        for img in sorted(list(d.glob("*.png")) + list(d.glob("*.jpg"))):
            frame = cv2.imread(str(img))
            if frame is not None:
                yield d.name, img, frame


def evaluate(classify, root: Path) -> int:
    """classify(frame) -> state_classifier.Result or (State, details)"""
    confusion = defaultdict(lambda: defaultdict(int))
    wrong, risky, total = [], [], 0

    for truth, path, frame in load_cases(root):
        r = classify(frame)
        total += 1
        
        # Hỗ trợ cả Result object và detector.detect() tuple
        if hasattr(r, "state"):
            pred_state = r.state
            margin = r.margin
            ranked = r.ranked
        elif isinstance(r, tuple):
            st, details = r
            pred_state = st.value if hasattr(st, "value") else str(st)
            margin = details.get("margin", 1.0)
            ranked = details.get("ranked", [(pred_state, details.get("score", 1.0))])
        else:
            pred_state = str(r)
            margin = 1.0
            ranked = []

        confusion[truth][pred_state] += 1
        if pred_state != truth:
            wrong.append((path, truth, pred_state, ranked))
        elif margin < LOW_MARGIN:
            risky.append((path, margin, ranked))

    print(f"\nTổng: {total} ảnh | Sai: {len(wrong)} | Sát ngưỡng: {len(risky)}\n")
    print("Ma trận nhầm lẫn (hàng = đúng, cột = nhận ra):")
    for truth, row in confusion.items():
        cells = ", ".join(f"{k}:{v}" for k, v in sorted(row.items(), key=lambda kv: -kv[1]))
        print(f"  {truth:24s} -> {cells}")

    if wrong:
        print("\nẢnh nhận SAI:")
        for path, truth, pred, ranked in wrong:
            print(f"  {path}\n    đúng={truth} | nhận={pred} | xếp hạng={ranked[:3] if ranked else 'N/A'}")
    if risky:
        print("\nẢnh đúng nhưng margin thấp (dễ sai khi game đổi nhẹ):")
        for path, margin, ranked in risky:
            print(f"  {path} | margin={margin:.2f} | {ranked[:2] if ranked else 'N/A'}")
    return 1 if wrong else 0


def suggest_thresholds(matcher, specs, root: Path):
    """Với mỗi neo: gom điểm trên ảnh đúng/sai, gợi ý ngưỡng hoặc cảnh báo chồng lấn."""
    cases = list(load_cases(root))
    if not cases:
        print("Không có ảnh trong thư mục fixture để tính toán ngưỡng.")
        return

    print("\nGợi ý ngưỡng:")
    for spec in specs:
        for a in spec.anchors:
            pos, neg = [], []
            for truth, _, frame in cases:
                s = matcher(frame, a.key, a.region)[0]
                (pos if truth == spec.state else neg).append(s)
            t = calibrate_threshold(pos, neg)
            tag = f"{t}" if t is not None else "CHỒNG LẤN - cắt lại template hoặc thêm neo phụ"
            print(f"  {spec.state:22s} {a.key:28s} hiện={a.threshold:<5} gợi ý={tag}")


if __name__ == "__main__":
    target_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT_DIR / "tests" / "fixtures" / "labeled"
    if not target_dir.exists():
        print(f"Thư mục không tồn tại: {target_dir}")
        print("Cấu trúc yêu cầu: <path>/<TEN_STATE>/<anh>.png")
        sys.exit(1)

    det = ScreenDetector()
    clf = StateClassifier(DEFAULT_STATE_SPECS, matcher=det.match)
    
    print(f"Đang đánh giá StateClassifier trên: {target_dir}")
    exit_code = evaluate(clf.classify, target_dir)
    
    if "--suggest" in sys.argv:
        suggest_thresholds(det.match, DEFAULT_STATE_SPECS, target_dir)
        
    sys.exit(exit_code)

