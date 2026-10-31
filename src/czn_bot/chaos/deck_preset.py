"""
Deck Preset management and schema validation for Chaos Zero Nightmare.
Pure Python dataclass implementation (no pydantic) to ensure lightweight PyInstaller builds.
"""
import os
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Set

from czn_bot.constants import PROJECT_ROOT

logger = logging.getLogger("ChaosBot.DeckPreset")

PRESETS_DIR = os.path.join(PROJECT_ROOT, "data", "presets")


@dataclass
class PresetCardRule:
    card_id: str
    min_copies: int = 1
    max_copies: int = 2
    priority: int = 80

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PresetCardRule":
        return cls(
            card_id=str(data.get("card_id", "")),
            min_copies=int(data.get("min_copies", 1)),
            max_copies=int(data.get("max_copies", 2)),
            priority=int(data.get("priority", 80)),
        )


@dataclass
class CharacterPreset:
    character: str
    archetype: str
    version: str = "1.0.0"
    core_cards: List[PresetCardRule] = field(default_factory=list)
    epiphany_targets: Dict[str, str] = field(default_factory=dict)
    removal_priority: List[str] = field(default_factory=list)
    max_deck_size: int = 10

    def validate(self, card_rules: Dict[str, Any]) -> None:
        """
        Validate all card IDs in this preset against card_rules.json.
        Raises ValueError if any referenced card_id does not exist.
        """
        if not card_rules:
            logger.warning(f"No card_rules provided for validating preset '{self.character}'")
            return

        cards_data = card_rules.get("cards", [])
        valid_ids: Set[str] = {c.get("id") for c in cards_data if c.get("id")}

        invalid_ids: List[str] = []

        # 1. Validate core_cards IDs
        for rule in self.core_cards:
            if rule.card_id not in valid_ids:
                invalid_ids.append(f"core_cards: {rule.card_id}")

        # 2. Validate epiphany_targets variant IDs
        for base_key, target_id in self.epiphany_targets.items():
            if target_id not in valid_ids:
                invalid_ids.append(f"epiphany_targets[{base_key}]: {target_id}")

        # 3. Validate removal_priority IDs
        for rem_id in self.removal_priority:
            if rem_id not in valid_ids:
                invalid_ids.append(f"removal_priority: {rem_id}")

        if invalid_ids:
            err_msg = (
                f"Preset '{self.character}' (version {self.version}) chứa ID thẻ không hợp lệ "
                f"hoặc không tồn tại trong card_rules.json:\n - " + "\n - ".join(invalid_ids)
            )
            logger.error(err_msg)
            raise ValueError(err_msg)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "character": self.character,
            "archetype": self.archetype,
            "version": self.version,
            "core_cards": [c.to_dict() for c in self.core_cards],
            "epiphany_targets": dict(self.epiphany_targets),
            "removal_priority": list(self.removal_priority),
            "max_deck_size": self.max_deck_size,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CharacterPreset":
        core_cards_raw = data.get("core_cards", [])
        core_cards = [
            PresetCardRule.from_dict(c) if isinstance(c, dict) else c
            for c in core_cards_raw
        ]
        return cls(
            character=str(data.get("character", "")),
            archetype=str(data.get("archetype", "default")),
            version=str(data.get("version", "1.0.0")),
            core_cards=core_cards,
            epiphany_targets=dict(data.get("epiphany_targets", {})),
            removal_priority=list(data.get("removal_priority", [])),
            max_deck_size=int(data.get("max_deck_size", 10)),
        )


def load_preset(
    filepath_or_name: str,
    card_rules: Optional[Dict[str, Any]] = None
) -> CharacterPreset:
    """
    Load a CharacterPreset from JSON file or by character name in data/presets/.
    Validates IDs against card_rules if provided.
    """
    path = filepath_or_name
    if not os.path.isfile(path):
        candidate = os.path.join(PRESETS_DIR, f"{filepath_or_name.lower()}.json")
        if os.path.isfile(candidate):
            path = candidate
        else:
            raise FileNotFoundError(f"Preset file not found: {filepath_or_name}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    preset = CharacterPreset.from_dict(data)
    if card_rules:
        preset.validate(card_rules)
    return preset


def save_preset(preset: CharacterPreset, filepath: str) -> None:
    """Save a CharacterPreset to JSON file."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(preset.to_dict(), f, indent=2, ensure_ascii=False)

