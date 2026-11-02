"""
czn_bot.chaos2.classifier - Phân loại màn hình dựa trên SCREEN_REGISTRY.
Hỗ trợ layout-aware scoring: tính điểm theo biến thể layout, chấm điểm mọi neo dương và neo âm.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple, Any
import numpy as np

from .registry import SCREEN_REGISTRY, ScreenDef, AnchorDef

logger = logging.getLogger("ChaosBot.Chaos2.Classifier")

Matcher = Callable[[np.ndarray, str, Optional[Tuple[int, int, int, int]]], Tuple[float, Optional[Tuple[int, int]]]]


@dataclass
class ClassificationResult:
    state: str
    confidence: float = 0.0
    margin: float = 0.0
    ranked: List[Tuple[str, float]] = field(default_factory=list)
    evidence: Dict[str, float] = field(default_factory=dict)
    all_anchor_scores: Dict[str, Dict[str, float]] = field(default_factory=dict)
    best_coords: Dict[str, Tuple[int, int]] = field(default_factory=dict)


class ChaosClassifier:
    def __init__(
        self,
        registry: Optional[Dict[str, ScreenDef]] = None,
        matcher: Optional[Matcher] = None,
        min_confidence: float = 0.35,
        min_margin: float = 0.15,
    ):
        self.registry = registry or SCREEN_REGISTRY
        self.matcher = matcher
        self.min_confidence = min_confidence
        self.min_margin = min_margin

    def set_matcher(self, matcher: Matcher):
        self.matcher = matcher

    def classify(self, screen: Optional[np.ndarray]) -> ClassificationResult:
        if screen is None or screen.size == 0 or self.matcher is None:
            return ClassificationResult(state="UNKNOWN")

        # Cache kết quả matchTemplate theo (key, region) để không tính trùng
        cache: Dict[Tuple[str, Optional[Tuple[int, int, int, int]]], Tuple[float, Optional[Tuple[int, int]]]] = {}
        evidence: Dict[str, float] = {}
        best_coords: Dict[str, Tuple[int, int]] = {}
        all_anchor_scores: Dict[str, Dict[str, float]] = {}

        def match_anchor(a: AnchorDef) -> Tuple[float, Optional[Tuple[int, int]]]:
            k = (a.key, a.region)
            if k not in cache:
                try:
                    res = self.matcher(screen, a.key, a.region)
                except Exception as ex:
                    logger.debug(f"Match error for anchor {a.key}: {ex}")
                    res = (0.0, None)

                if isinstance(res, (tuple, list)) and len(res) >= 2:
                    score, pt = float(res[0]), res[1]
                elif isinstance(res, (int, float)):
                    score, pt = float(res), None
                else:
                    score, pt = 0.0, None

                cache[k] = (score, pt)
                evidence[a.key] = max(evidence.get(a.key, 0.0), score)
                if pt and (a.key not in best_coords or score > evidence.get(a.key, 0.0)):
                    best_coords[a.key] = pt
            return cache[k]

        state_scores: Dict[str, float] = {}

        for screen_id, sdef in self.registry.items():
            all_anchor_scores[screen_id] = {}

            # 1. Đo tất cả neo âm trước
            negative_triggered = False
            for na in sdef.negative_anchors:
                sc, _ = match_anchor(na)
                all_anchor_scores[screen_id][f"NEG_{na.key}"] = sc
                if sc >= na.threshold:
                    negative_triggered = True

            # 2. Đo tất cả neo dương theo biến thể layout
            best_layout_score = 0.0
            for layout in sdef.positive_layouts:
                total_w = sum(pa.weight for pa in layout) or 1.0
                hits = []
                accum_score = 0.0
                for pa in layout:
                    sc, _ = match_anchor(pa)
                    all_anchor_scores[screen_id][f"POS_{pa.key}"] = sc
                    if sc >= pa.threshold:
                        hits.append(pa)
                        norm = min(1.0, (sc - pa.threshold) / max(1e-6, 1.0 - pa.threshold) * 0.5 + 0.5)
                        accum_score += pa.weight * norm

                if hits:
                    layout_norm = accum_score / total_w
                    if layout_norm > best_layout_score:
                        best_layout_score = layout_norm

            if negative_triggered:
                continue

            if best_layout_score > 0.0:
                state_scores[screen_id] = best_layout_score

        if not state_scores:
            return ClassificationResult(
                state="UNKNOWN",
                evidence=evidence,
                all_anchor_scores=all_anchor_scores,
                best_coords=best_coords,
            )

        ranked = sorted(state_scores.items(), key=lambda x: x[1], reverse=True)
        top_state, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = top_score - second_score

        if top_score < self.min_confidence:
            return ClassificationResult(
                state="UNKNOWN",
                confidence=top_score,
                margin=margin,
                ranked=ranked,
                evidence=evidence,
                all_anchor_scores=all_anchor_scores,
                best_coords=best_coords,
            )

        if len(ranked) > 1 and margin < self.min_margin:
            return ClassificationResult(
                state="AMBIGUOUS",
                confidence=top_score,
                margin=margin,
                ranked=ranked,
                evidence=evidence,
                all_anchor_scores=all_anchor_scores,
                best_coords=best_coords,
            )

        return ClassificationResult(
            state=top_state,
            confidence=top_score,
            margin=margin,
            ranked=ranked,
            evidence=evidence,
            all_anchor_scores=all_anchor_scores,
            best_coords=best_coords,
        )
