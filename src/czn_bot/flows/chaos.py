"""
Chaos Mode Flow (Chế độ Chaos).
Autonomous decision-making for Chaos Mode:
- DAG Mini-map pathfinding (normal/elite/rest/boss) with survival & balanced strategies
- Auto card selection (Epiphany & Card Rewards) with AI and Heuristic fallback
- Auto equipment selection (Tier S > A > B) matching 27 Swamp of Judgment items
- Safe Zone Campfire: ALWAYS chooses Rest (Heal team), never skips
- Auto-skips dialogues and events during Chaos progression
"""
from typing import Optional, Dict, Any, List, Tuple
import logging
import numpy as np

from czn_bot.states import State
from czn_bot.coords import TAP_COORDS
from czn_bot.flows.base import Flow, Action
from czn_bot.chaos.pathfinder import (
    select_best_island,
    IslandChoice,
    get_strategy_profile,
)
from czn_bot.vision.hp_reader import get_team_hp
from czn_bot.vision.map_reader import parse_chaos_minimap, detect_3d_island_coords
from czn_bot.chaos.rules import ChaosRuleManager
from czn_bot.chaos.decisions import ChaosVision, ResourceInfo
from czn_bot.chaos.ai_brain import ChaosAIBrain

logger = logging.getLogger("ChaosBot.ChaosFlow")


class ChaosFlow(Flow):
    def __init__(
        self,
        strategy: str = "balanced",
        auto_pick_epiphany: bool = True,
        enable_dynamic_islands: bool = True,
        rule_manager: Optional[ChaosRuleManager] = None,
        ai_brain: Optional[ChaosAIBrain] = None,
        vision: Optional[ChaosVision] = None,
        max_matches: Optional[int] = None,
        max_map_retries: int = 5,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.strategy = strategy
        self.auto_pick_epiphany = auto_pick_epiphany
        self.enable_dynamic_islands = enable_dynamic_islands
        self.rule_manager = rule_manager or ChaosRuleManager()
        self.ai_brain = ai_brain or ChaosAIBrain(rule_manager=self.rule_manager)
        self.vision = vision or ChaosVision(rule_manager=self.rule_manager)
        self.max_matches = max_matches
        self.matches_completed = 0
        self.max_map_retries = max_map_retries
        self._minimap_retry_count = 0
        self._map_tap_attempts = 0

    def _resolve_island_static_coord(
        self,
        island: IslandChoice,
        num_roots: int,
        available_islands: Optional[set] = None
    ) -> Tuple[Tuple[int, int], str]:
        available = available_islands or set()
        if num_roots == 1:
            return TAP_COORDS["chaos_island_1_middle"], "Đảo Duy Nhất"
        if num_roots == 2:
            if IslandChoice.TOP in available and IslandChoice.MIDDLE in available:
                if island == IslandChoice.TOP:
                    return TAP_COORDS["chaos_island_2_top"], "Đảo Trên"
                return TAP_COORDS["chaos_island_2_middle"], "Đảo Giữa"
            elif IslandChoice.MIDDLE in available and IslandChoice.BOTTOM in available:
                if island == IslandChoice.MIDDLE:
                    return TAP_COORDS["chaos_island_2_middle"], "Đảo Giữa"
                return TAP_COORDS["chaos_island_2_bottom"], "Đảo Dưới"
            else:
                if island == IslandChoice.TOP:
                    return TAP_COORDS["chaos_island_2_top"], "Đảo Trên"
                return TAP_COORDS["chaos_island_2_bottom"], "Đảo Dưới"
        # Default 3 islands
        if island == IslandChoice.TOP:
            return TAP_COORDS["chaos_island_3_top"], "Đảo Trên"
        elif island == IslandChoice.BOTTOM:
            return TAP_COORDS["chaos_island_3_bottom"], "Đảo Dưới"
        return TAP_COORDS["chaos_island_3_middle"], "Đảo Giữa"

    def handle(self, state: State, details: Dict[str, Any], screen: Optional[np.ndarray]) -> Action:
        if state == State.IN_MATCH:
            return Action.none(name="In Match (waiting for battle completion)")

        # 1. CHAOS_MAP: Mini-map DAG pathfinding & 3D island detection
        if state == State.CHAOS_MAP:
            if screen is None or screen.size == 0:
                return Action.none(name="Chaos Map: Waiting for valid frame")

            hp_percent, is_low_hp = get_team_hp(screen)
            roots, adj, nodes, boss_ids = parse_chaos_minimap(screen)

            # Item 1: Khi camera đang lia hoặc minimap đang chuyển cảnh, chờ 3-5 khung (thay vì dừng bot ngay)
            if not roots:
                self._minimap_retry_count = getattr(self, "_minimap_retry_count", 0) + 1
                if self._minimap_retry_count < self.max_map_retries:
                    return Action.wait(1.0, name=f"Chờ minimap ổn định ({self._minimap_retry_count}/{self.max_map_retries})")
                self._minimap_retry_count = 0
                return Action.stop(reason=f"Không thể phân tích minimap đường đi Chaos sau {self.max_map_retries} lần thử")

            self._minimap_retry_count = 0

            # Item 7: Kiểm soát số lần thử tap liên tiếp trên bản đồ
            self._map_tap_attempts = getattr(self, "_map_tap_attempts", 0) + 1
            if self._map_tap_attempts > 2:
                # Chờ màn hình ổn định rồi mới nhận diện lại, tuyệt đối không trừ 40px bừa bãi
                self._map_tap_attempts = 0
                return Action.wait(1.5, name="Chờ camera/màn hình bản đồ ổn định rồi nhận diện lại")

            best_island, evaluations = select_best_island(
                roots, adj, nodes, boss_ids, hp_percent, strategy=self.strategy
            )

            if best_island is None:
                if roots and len(roots) == 1:
                    best_island = list(roots.keys())[0]
                else:
                    return Action.stop(reason="Không tìm thấy nhánh đường an toàn đến Boss")

            # AI decision override if available
            if self.rule_manager.get_api_key():
                try:
                    res_info = ResourceInfo(hp_percent=hp_percent, is_low_hp=is_low_hp, credits=0)
                    ai_decision = self.ai_brain.decide_island(evaluations, res_info, strategy_mode=self.strategy)
                    if ai_decision and "target_island" in ai_decision:
                        t_str = str(ai_decision["target_island"]).lower()
                        for cand in roots.keys():
                            if cand.value.lower() == t_str:
                                best_island = cand
                                break
                except Exception as e:
                    logger.debug(f"AI decide island error: {e}")

            static_coord, name = self._resolve_island_static_coord(
                best_island, len(roots), available_islands=set(roots.keys())
            )
            target_coord = static_coord

            # Item 7: Ưu tiên nhận diện 3D đảo thực tế
            if self.enable_dynamic_islands:
                try:
                    dyn_coords = detect_3d_island_coords(screen, expected_choices=list(roots.keys()))
                    if best_island in dyn_coords:
                        target_coord = dyn_coords[best_island]
                except Exception as e:
                    logger.debug(f"Dynamic 3D island detection error: {e}")

            best_eval = evaluations.get(best_island)
            score = best_eval.best_score if (best_eval and best_eval.best_score != float("-inf")) else 0.0

            return Action.tap(
                target_coord[0], target_coord[1],
                name=f"Select {name} ({best_island.value})",
                island=best_island.value,
                score=score,
                hp_percent=hp_percent
            )

        # 2. CHAOS_AFTER_BATTLE: Click Leave button
        if state == State.CHAOS_AFTER_BATTLE:
            if self.max_matches is not None and self.matches_completed >= self.max_matches:
                return Action.stop(reason=f"Đã đạt giới hạn số trận Chaos ({self.max_matches})", max_stages=True)

            self.matches_completed += 1
            leave_coord = details.get("leave_coord") or TAP_COORDS["chaos_leave_button"]
            score = details.get("score", 0.95)
            return Action.tap(
                *leave_coord,
                name="Chaos Leave Button",
                stage_number=self.matches_completed,
                score=score,
                expected_words=["leave", "rời", "thoát", "continue", "tiếp", "confirm", "settlement"]
            )

        # 3. CHAOS_EQUIPMENT: Autonomous equipment selection & confirmation (Item 5)
        if state == State.CHAOS_EQUIPMENT:
            equipments = self.vision.extract_equipments(screen) if screen is not None else []
            best_equip = equipments[0] if equipments else None

            if best_equip:
                tap_x, tap_y = best_equip.tap_coord
                equip_name = best_equip.name
            else:
                tap_x, tap_y = (500, 350)
                equip_name = "Default Equipment Slot 1"

            confirm_coord = details.get("confirm_coord") or TAP_COORDS.get("equipment_confirm", (1360, 806))

            # Sequence: Chọn trang bị -> Gán nhân vật (1150, 520) -> Xác nhận
            return Action.tap(
                tap_x, tap_y,
                name=f"Equip {equip_name}",
                extra_actions=[
                    ("tap", (1150, 520)),
                    ("tap", confirm_coord),
                ]
            )

        # 4. CHAOS_SAFE_ZONE: Always select Rest (Heal team), NEVER skip when rest is available! (Item 4)
        if state == State.CHAOS_SAFE_ZONE:
            is_modal = details.get("is_modal_open", False)
            confirm_coord = details.get("confirm_coord") or TAP_COORDS.get("chaos_safe_zone_confirm", (1055, 642))
            rest_coord = details.get("rest_coord") or TAP_COORDS.get("chaos_safe_zone_rest", (455, 690))
            skip_coord = details.get("skip_coord") or TAP_COORDS.get("chaos_safe_zone_skip", (1415, 825))
            has_rest = details.get("has_rest_btn", False)
            score = details.get("score", 0.95)

            # Trường hợp 1: Popup Modal Rest đang mở (Ảnh 2) -> Bấm nút Confirm màu cam
            if is_modal:
                return Action.tap(
                    confirm_coord[0], confirm_coord[1],
                    name="Safe Zone Confirm Rest (Modal Open)",
                    score=score,
                )

            # Trường hợp 2: Đang ở màn hình Camp (Ảnh 1) và còn nút Rest
            if has_rest or not details.get("interactions_exhausted", False):
                return Action.tap(
                    rest_coord[0], rest_coord[1],
                    name="Safe Zone Rest (Always Heal Team)",
                    score=score,
                    extra_actions=[
                        ("tap", confirm_coord),
                    ]
                )

            # Trường hợp 3: Đã hồi phục xong / hết lượt Rest -> Bấm Skip
            return Action.tap(
                skip_coord[0], skip_coord[1],
                name="Safe Zone Skip (No Rest Available)",
                score=score,
            )

        # 4b. CHAOS_EVENT: Random Event Encounters (Poacher wager, dialog events, quizzes)
        if state == State.CHAOS_EVENT:
            choices = self.vision.extract_event_choices(screen) if screen is not None else []
            res = self.vision.extract_resources(screen) if screen is not None else ResourceInfo(1.0, False, 0)

            if choices:
                decision = self.ai_brain.decide_event(choices, res)
                target_idx = decision.get("target_index", 0)
                if target_idx < len(choices):
                    tap_coord = choices[target_idx].tap_coord
                    choice_name = choices[target_idx].name or f"Choice {target_idx + 1}"
                    choice_text = choices[target_idx].text
                    matched_ev = choices[target_idx].matched_event_name
                    score = choices[target_idx].priority_score
                else:
                    tap_coord = (795, 765)
                    choice_name = "Default Choice"
                    choice_text = ""
                    matched_ev = ""
                    score = 5
            else:
                tap_coord = (795, 765)
                choice_name = "Default Middle Choice"
                choice_text = ""
                matched_ev = ""
                score = 5

            # Game cơ chế: Muốn chọn event phải nhấn 2 lần vào ô lựa chọn
            # Lần 1: Action tap chính tại tap_coord
            # Lần 2: extra_actions đầu tiên chạm lại chính tap_coord để xác nhận
            extra_actions = [("tap", tap_coord)]

            if screen is not None:
                battle_btn = self.vision.find_action_button(screen, action_type="battle")
                if battle_btn and battle_btn != tap_coord:
                    extra_actions.append(("tap", battle_btn))
                else:
                    confirm_btn = self.vision.find_action_button(screen, action_type="confirm")
                    if confirm_btn and confirm_btn != tap_coord:
                        extra_actions.append(("tap", confirm_btn))

            return Action.tap(
                tap_coord[0], tap_coord[1],
                name=f"Event Choice (Double Tap): {choice_name} ({choice_text[:30]})" if choice_text else f"Event Choice (Double Tap): {choice_name}",
                score=score,
                extra_actions=extra_actions,
                extra={"matched_event": matched_ev, "choice_text": choice_text}
            )

        # 5. CHAOS_CHOOSE_EPIPHANY: Auto pick card or event choice immediately (Item 3)
        if state == State.CHAOS_CHOOSE_EPIPHANY:
            if not self.auto_pick_epiphany:
                return Action.none(name="Card Selection (Manual Wait)")

            self._epiphany_wait_count = getattr(self, "_epiphany_wait_count", 0) + 1
            if self._epiphany_wait_count < 2:
                return Action.none(name="Wait for card animation to stabilize")

            self._epiphany_wait_count = 0
            epiphany_type = details.get("type") or details.get("epiphany_type", "epiphany")
            res = self.vision.extract_resources(screen) if screen is not None else ResourceInfo(1.0, False, 0)

            # Sub-screen 0: card_reward (1 card on left, assign to 1 of 3 combatants on right)
            if epiphany_type == "card_reward":
                card_info = self.vision.extract_single_card_reward(screen) if screen is not None else {"title": "Card Reward"}
                card_title = card_info.get("title", "Card Reward")
                # Default target: middle combatant (index 1), can be directed by deck engine
                combatant_idx = 1
                combatant_coords = [
                    TAP_COORDS.get("chaos_card_reward_combatant_1", (800, 300)),
                    TAP_COORDS.get("chaos_card_reward_combatant_2", (800, 500)),
                    TAP_COORDS.get("chaos_card_reward_combatant_3", (800, 700)),
                ]
                tap_coord = combatant_coords[combatant_idx]
                confirm_coord = TAP_COORDS.get("chaos_card_reward_confirm", (1450, 838))
                return Action.tap(
                    tap_coord[0], tap_coord[1],
                    name=f"Card Reward: Assign '{card_title}' to Combatant {combatant_idx + 1}",
                    extra_actions=[
                        ("tap", confirm_coord),
                    ],
                    extra={"card_title": card_title, "combatant_idx": combatant_idx}
                )

            # Sub-screen 1: choose_fate (Lựa chọn định mệnh / Sự kiện)
            if epiphany_type == "choose_fate":
                choices = self.vision.extract_event_choices(screen) if screen is not None else []
                if choices:
                    decision = self.ai_brain.decide_event(choices, res)
                    target_idx = decision.get("target_index", 0)
                    tap_coord = choices[target_idx].tap_coord if target_idx < len(choices) else (800, 360)
                    choice_name = choices[target_idx].name if target_idx < len(choices) else "Option 1"
                else:
                    tap_coord = (800, 360)
                    choice_name = "Default Fate Choice"
                return Action.tap(
                    tap_coord[0], tap_coord[1],
                    name=f"Choose Fate: {choice_name}",
                    extra_actions=[("tap", (1425, 835))]
                )

            # Sub-screen 2: select_attribute (Chọn chỉ số thưởng)
            if epiphany_type == "select_attribute":
                return Action.tap(
                    800, 500,
                    name="Select Attribute (Middle Option)",
                    extra_actions=[("tap", (1425, 835))]
                )

            # Sub-screen 3: remove_card (Thanh lọc thẻ hoặc Skip nếu không có thẻ rác)
            if epiphany_type == "remove_card":
                visible = self.vision.extract_remove_cards(screen) if screen is not None else []
                target_coord = (530, 300)
                card_name = "Basic Card"
                reason = "Xóa thẻ cơ bản mặc định (Slot 0)"

                if visible and hasattr(self, "ai_brain") and getattr(self.ai_brain, "deck_evaluator", None):
                    names = [c["title"] for c in visible]
                    decision, target_slot, eval_reason = self.ai_brain.deck_evaluator.evaluate_card_removal(names, "Rossweisse")
                    if decision == "skip":
                        skip_coord = TAP_COORDS.get("chaos_remove_card_skip", (1230, 837))
                        return Action.tap(
                            skip_coord[0], skip_coord[1],
                            name=f"Remove Card: Skip ({eval_reason})",
                            extra={"decision": "skip", "reason": eval_reason}
                        )
                    elif target_slot is not None and target_slot < len(visible):
                        target_coord = visible[target_slot]["tap_coord"]
                        card_name = visible[target_slot]["title"]
                        reason = eval_reason

                remove_btn = TAP_COORDS.get("chaos_remove_card_confirm", (1498, 838))
                return Action.tap(
                    target_coord[0], target_coord[1],
                    name=f"Remove Card: {card_name}",
                    extra_actions=[("tap", remove_btn)],
                    extra={"decision": "remove", "card_name": card_name, "reason": reason}
                )

            # Sub-screen 4: etched_memory (Khắc ký ức)
            if epiphany_type == "etched_memory":
                return Action.tap(
                    800, 500,
                    name="Accept Etched Memory",
                    extra_actions=[("tap", (800, 850))]
                )

            # Sub-screen 5: event choices (Sự kiện có danh sách lựa chọn)
            choices = self.vision.extract_event_choices(screen) if screen is not None else []
            if choices and len(choices) >= 2:
                decision = self.ai_brain.decide_event(choices, res)
                target_idx = decision.get("target_index", 0)
                tap_coord = choices[target_idx].tap_coord if target_idx < len(choices) else (800, 360)
                choice_name = choices[target_idx].name if target_idx < len(choices) else "Option 1"
                return Action.tap(
                    tap_coord[0], tap_coord[1],
                    name=f"Event Choice: {choice_name}",
                    extra_actions=[
                        ("tap", (1425, 835)),
                    ]
                )

            # Sub-screen 6: standard 3-card reward / Epiphany
            cards = self.vision.extract_cards(screen, num_cards=3) if screen is not None else []
            decision = self.ai_brain.decide_card(cards, res)
            target_idx = decision.get("target_index", 1)
            tap_coord = cards[target_idx].tap_coord if target_idx < len(cards) else (800, 450)
            card_title = cards[target_idx].title if target_idx < len(cards) and cards[target_idx].title else f"Card {target_idx + 1}"

            return Action.tap(
                tap_coord[0], tap_coord[1],
                name=f"Auto Pick Card: {card_title}",
                extra_actions=[
                    ("tap", (1425, 835)),
                ]
            )

        # 6. CHAOS_OBTAIN_REWARD: Tap Obtain button
        if state == State.CHAOS_OBTAIN_REWARD:
            obtain_coord = details.get("obtain_coord") or TAP_COORDS["chaos_obtain_button"]
            score = details.get("score", 0.95)
            return Action.tap(
                *obtain_coord,
                name="Obtain Reward Button",
                score=score,
                expected_words=["obtain", "skip", "nhận", "thu thập", "bỏ qua", "chạm", "tiếp tục"]
            )

        # 7. STORY_DIALOGUE: In Chaos Mode, always fast-forward dialogues
        if state == State.STORY_DIALOGUE:
            skip_coord = details.get("skip_coord") or TAP_COORDS.get("story_dialogue_skip", (1272, 48))
            auto_coord = details.get("auto_coord") or TAP_COORDS.get("story_dialogue_auto", (1395, 48))
            return Action.tap(
                *auto_coord,
                name="Chaos Dialogue Fast-Forward",
                extra_actions=[
                    ("tap", skip_coord),
                    ("tap", skip_coord),
                    ("tap", skip_coord),
                    ("tap", (800, 800)),
                    ("tap", TAP_COORDS.get("story_skip_confirm", (950, 550))),
                ],
                extra={"dialogue_skip": True}
            )

        # 8. Pre-match lobby
        if state in (State.PRE_MATCH_MISSION, State.PRE_MATCH_TEAM):
            coord = details.get("coord")
            if not coord:
                coord = TAP_COORDS["enter_team"] if state == State.PRE_MATCH_TEAM else TAP_COORDS["enter_mission"]
            return Action.tap(*coord, name=f"Enter {state.value}")

        if state in (State.POPUP_EFFECT, State.POPUP_DRAW_PILE, State.POPUP_STAGE_INFO, State.POPUP_PAUSE):
            close_coord = details.get("close_coord") or TAP_COORDS["close_x_default"]
            return Action.tap(*close_coord, name=f"Close {state.value}")

        if state == State.POPUP_MONSTER_INFO:
            coord = details.get("close_coord") or TAP_COORDS["close_monster_info"]
            return Action.tap(*coord, name="Dismiss Monster Info")

        if state == State.TRANSITIONING:
            return Action.none(name="Transitioning Animation")

        return Action.none(name="Chaos Flow: Idle")
