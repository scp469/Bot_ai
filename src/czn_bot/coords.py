"""
Coordinate constants and ROIs for Chaos Zero Nightmare Bot.
Target resolution: 1600x900.
"""

# Tap coordinates (x, y) for actions on 1600x900
TAP_COORDS = {
    # Default top-right popup close 'X'
    "close_x_default":        (1535, 50),
    "close_monster_info":     (1100, 450),  # Dismiss popup by tapping side area
    "left_button":            (1070, 830),  # Retry or Next Mission button center
    "right_button":           (1405, 830),  # Confirm button center
    "enter_mission":          (1290, 830),  # Enter button on mission info panel
    "enter_team":             (1470, 835),  # Enter button on team formation screen

    # Chaos Mode: Island coordinates when 3 islands appear
    "chaos_island_3_top":     (1210, 140),
    "chaos_island_3_middle":  (1330, 420),
    "chaos_island_3_bottom":  (1350, 680),

    # Chaos Mode: Island coordinates when 2 islands appear
    "chaos_island_2_top":     (1210, 140),
    "chaos_island_2_bottom":  (1430, 400),
    "chaos_island_2_middle":  (1430, 400),

    # Chaos Mode: Island coordinate when 1 island appears
    "chaos_island_1_middle":  (1280, 520),

    # Fallback island coordinates
    "chaos_island_top":       (1210, 140),
    "chaos_island_middle":    (1330, 420),
    "chaos_island_bottom":    (1430, 680),

    # Chaos Mode: Buttons
    "chaos_leave_button":     (1426, 828),  # Orange Leave button after Chaos battle
    "chaos_continue_button":  (1415, 825),  # Continue button
    "chaos_obtain_button":    (1380, 830),  # Obtain button
    "chaos_settlement_button": (1425, 827), # Settlement button
    "chaos_safe_zone_rest":   (455, 690),   # Rest button (Heal team) in Safe Zone
    "chaos_safe_zone_skip":   (1415, 825),  # Skip button (do NOT tap in auto rest!)
    "chaos_safe_zone_confirm": (1055, 642), # Modal confirmation in Safe Zone
    "chaos_safe_zone_cancel":  (544, 642),  # Modal cancel in Safe Zone
    "equipment_confirm":      (1360, 806),  # Confirm button for Chaos equipment screen
    "modal_close_button":     (800, 837),   # Close button on info modal
    "tap_to_close":           (800, 850),   # Tap to close dialog
    "chaos_card_reward_combatant_1": (800, 300),  # Top combatant on Card Reward screen
    "chaos_card_reward_combatant_2": (800, 500),  # Middle combatant on Card Reward screen
    "chaos_card_reward_combatant_3": (800, 700),  # Bottom combatant on Card Reward screen
    "chaos_card_reward_confirm":     (1450, 838), # Confirm button on Card Reward screen
    "chaos_remove_card_skip":        (1230, 837), # Skip button [>| Skip] on Remove Card screen
    "chaos_remove_card_confirm":     (1498, 838), # Remove button on Remove Card screen
    "chaos_event_choice_3_left":   (375, 765),  # Event choice 1 (left) in 3-choice layout
    "chaos_event_choice_3_middle": (795, 765),  # Event choice 2 (middle) in 3-choice layout
    "chaos_event_choice_3_right":  (1215, 765), # Event choice 3 (right) in 3-choice layout
    "chaos_event_choice_2_left":   (520, 765),  # Event choice 1 in 2-choice layout
    "chaos_event_choice_2_right":  (1080, 765), # Event choice 2 in 2-choice layout
    "chaos_event_battle_button":   (1475, 830), # Event encounter / sword battle button

    # Story Mode coordinates
    "story_dialogue_skip":    (1272, 48),   # Skip dialogue button [▷|]
    "story_dialogue_auto":    (1395, 48),   # Auto dialogue button [>>]
    "story_skip_confirm":     (950, 550),   # Confirm popup "Skip this story?"
    "story_chapter_next":     (1194, 40),   # Next chapter button [>]
    "story_chapter_prev":     (417, 40),    # Previous chapter button [<]
}

# ── Regions of Interest (ROI) (x, y, w, h) ────────────────────
ROIS = {
    "hp_bar":                 (34, 32, 608, 6),
    "minimap":                (20, 570, 640, 320),
    "equipment_title":        (650, 70, 350, 110),
    "equipment_grid":         (400, 250, 800, 400),
    "safe_zone_rest_btn":     (250, 620, 350, 130),
    "safe_zone_confirm_btn":  (800, 590, 510, 100),
    "safe_zone_skip_btn":     (1200, 750, 380, 140),
    "chaos_event_banner":     (150, 130, 1300, 150),
    "chaos_event_badge":      (0, 100, 160, 200),
    "chaos_event_bottom_cards": (100, 640, 1400, 240),
    "story_title":            (40, 20, 300, 80),
    "story_dialogue_controls": (1200, 20, 380, 70),
}

