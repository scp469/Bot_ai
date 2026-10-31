"""
Session statistics and performance tracker for Chaos Zero Nightmare Bot.
Tracks win/loss, matches, island distributions, HP averages, and path quality scores.
"""
import os
import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

from czn_bot.constants import LOGS_DIR


class StatsTracker:
    def __init__(self) -> None:
        self.session_id: str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.start_time: float = time.time()
        self.end_time: Optional[float] = None
        self.stop_reason: Optional[str] = None

        # Counters
        self.actions_done: int = 0
        self.retries_done: int = 0
        self.matches_completed: int = 0
        self.unknown_encounters: int = 0
        self.stamina_exhausted: bool = False

        # Chaos Mode specific metrics
        self.island_picks: Dict[str, int] = {
            "top": 0,
            "middle": 0,
            "bottom": 0,
            "single": 0,
        }
        self.path_scores: List[float] = []
        self.hp_samples: List[float] = []

    def start_session(self) -> None:
        """Reset counters and start a fresh tracking session."""
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.start_time = time.time()
        self.end_time = None
        self.stop_reason = None
        self.actions_done = 0
        self.retries_done = 0
        self.matches_completed = 0
        self.unknown_encounters = 0
        self.stamina_exhausted = False
        self.island_picks = {"top": 0, "middle": 0, "bottom": 0, "single": 0}
        self.path_scores.clear()
        self.hp_samples.clear()

    def record_action(self) -> None:
        """Record an ADB tap interaction."""
        self.actions_done += 1

    def record_retry(self) -> None:
        """Record a completed match retry."""
        self.retries_done += 1
        self.matches_completed += 1

    def record_match_completed(self) -> None:
        """Record a completed match (e.g. Next Mission)."""
        self.matches_completed += 1

    def record_unknown(self) -> None:
        """Record an unrecognized screen encounter."""
        self.unknown_encounters += 1

    def record_stamina_exhausted(self) -> None:
        """Record stamina exhaustion."""
        self.stamina_exhausted = True

    def record_chaos_choice(
        self,
        island_name: str,
        score: float,
        hp_percent: float
    ) -> None:
        """Record an island choice, path score, and current team HP."""
        isl_key = island_name.lower()
        if "top" in isl_key or "trên" in isl_key:
            self.island_picks["top"] += 1
        elif "bottom" in isl_key or "dưới" in isl_key:
            self.island_picks["bottom"] += 1
        elif "single" in isl_key or "duy nhất" in isl_key:
            self.island_picks["single"] += 1
        else:
            self.island_picks["middle"] += 1

        self.path_scores.append(float(score))
        self.hp_samples.append(float(hp_percent))

    def record_stop(self, reason: str) -> None:
        """Record session termination with final reason."""
        self.end_time = time.time()
        self.stop_reason = reason
        if "hết thể lực" in reason.lower():
            self.stamina_exhausted = True

    @property
    def duration_seconds(self) -> float:
        """Calculate total session active duration in seconds."""
        end = self.end_time or time.time()
        return max(0.0, end - self.start_time)

    @property
    def avg_path_score(self) -> float:
        """Calculate average Chaos path evaluation score."""
        return sum(self.path_scores) / len(self.path_scores) if self.path_scores else 0.0

    @property
    def avg_team_hp(self) -> float:
        """Calculate average team HP at path decision points."""
        return sum(self.hp_samples) / len(self.hp_samples) if self.hp_samples else 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert session statistics to a dictionary."""
        return {
            "session_id": self.session_id,
            "duration_seconds": round(self.duration_seconds, 1),
            "start_time": datetime.fromtimestamp(self.start_time).strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": (
                datetime.fromtimestamp(self.end_time).strftime("%Y-%m-%d %H:%M:%S")
                if self.end_time else None
            ),
            "stop_reason": self.stop_reason,
            "matches_completed": self.matches_completed,
            "retries_done": self.retries_done,
            "actions_done": self.actions_done,
            "unknown_encounters": self.unknown_encounters,
            "stamina_exhausted": self.stamina_exhausted,
            "chaos_stats": {
                "total_islands_selected": sum(self.island_picks.values()),
                "island_distribution": dict(self.island_picks),
                "avg_path_score": round(self.avg_path_score, 2),
                "avg_team_hp_percent": round(self.avg_team_hp * 100, 1),
            }
        }

    def format_summary(self) -> str:
        """Generate human-readable end-of-session summary."""
        d = self.to_dict()
        dur_mins = int(self.duration_seconds // 60)
        dur_secs = int(self.duration_seconds % 60)
        dur_str = f"{dur_mins}m {dur_secs}s" if dur_mins > 0 else f"{dur_secs}s"

        lines = [
            "================ BÁO CÁO PHIÊN CHẠY BOT ================",
            f"Mã phiên: {d['session_id']}",
            f"Thời gian hoạt động: {dur_str} (bắt đầu: {d['start_time']})",
            f"Trạng thái kết thúc: {d['stop_reason'] or 'Đang chạy'}",
            f"Số trận hoàn thành: {d['matches_completed']} (Retries: {d['retries_done']})",
            f"Tổng số tương tác (taps): {d['actions_done']}",
            f"Gặp trạng thái UNKNOWN: {d['unknown_encounters']} lần",
            f"Hết thể lực: {'CÓ ⚠️' if d['stamina_exhausted'] else 'Không'}",
        ]

        chaos = d["chaos_stats"]
        if chaos["total_islands_selected"] > 0:
            lines.extend([
                "--- Thống kê Chế độ Chaos ---",
                f"Tổng số đảo đã chọn: {chaos['total_islands_selected']}",
                (
                    f"Phân bổ chọn đảo: Top={chaos['island_distribution']['top']} | "
                    f"Mid={chaos['island_distribution']['middle']} | "
                    f"Bot={chaos['island_distribution']['bottom']} | "
                    f"Single={chaos['island_distribution']['single']}"
                ),
                f"Máu đội trung bình khi chọn đường: {chaos['avg_team_hp_percent']}%",
                f"Điểm số đường đi trung bình: {chaos['avg_path_score']}",
            ])
        lines.append("========================================================")
        return "\n".join(lines)

    def export_json(self, filepath: Optional[str] = None) -> str:
        """Export session statistics to a JSON file."""
        if not filepath:
            os.makedirs(LOGS_DIR, exist_ok=True)
            filepath = os.path.join(LOGS_DIR, f"stats_session_{self.session_id}.json")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return filepath

