"""
Deck State Tracker with In-Memory Count and JSONL Event Logging for Chaos Zero Nightmare.
Pure Python, zero-dependency Event Sourcing tracker per run.
"""
import os
import json
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from czn_bot.constants import PROJECT_ROOT

logger = logging.getLogger("ChaosBot.DeckState")

DECKS_LOG_DIR = os.path.join(PROJECT_ROOT, "logs", "decks")


@dataclass
class DeckCard:
    card_id: str
    card_name: str
    character: str
    variant: str = "Base"
    is_copied: bool = False


class DeckState:
    """
    Manages in-memory state of character decks during a Chaos run,
    logging all mutations (pick, remove, upgrade, copy) to a JSONL event log.
    """

    def __init__(self, run_id: Optional[str] = None, log_dir: str = DECKS_LOG_DIR):
        self.run_id = run_id or f"run_{int(time.time())}"
        self.log_dir = log_dir
        self.log_file = os.path.join(self.log_dir, f"{self.run_id}.jsonl")
        self._decks: Dict[str, List[DeckCard]] = {}
        self._history: List[Dict[str, Any]] = []

    def initialize_team(self, team_decks: Dict[str, List[Dict[str, str]]]) -> None:
        """
        Initialize starting decks for characters.
        team_decks: { "Rossweisse": [{"card_id": "...", "card_name": "..."}, ...] }
        """
        for char, cards in team_decks.items():
            self._decks[char] = [
                DeckCard(
                    card_id=c.get("card_id", ""),
                    card_name=c.get("card_name", ""),
                    character=char,
                    variant=c.get("variant", "Base")
                )
                for c in cards
            ]
            self._record_event("INITIALIZE_DECK", char, details={"initial_size": len(cards)})

    def get_deck(self, character: str) -> List[DeckCard]:
        return list(self._decks.get(character, []))

    def get_deck_size(self, character: str) -> int:
        return len(self._decks.get(character, []))

    def get_total_deck_size(self) -> int:
        return sum(len(deck) for deck in self._decks.values())

    def count_copies(self, character: str, card_id: str) -> int:
        return sum(1 for c in self._decks.get(character, []) if c.card_id == card_id)

    def has_card(self, character: str, card_id: str) -> bool:
        return any(c.card_id == card_id for c in self._decks.get(character, []))

    def record_card_picked(
        self,
        character: str,
        card_id: str,
        card_name: str,
        variant: str = "Base",
        source: str = "card_reward"
    ) -> None:
        """Record a card being added to a character's deck."""
        if character not in self._decks:
            self._decks[character] = []

        card = DeckCard(card_id=card_id, card_name=card_name, character=character, variant=variant)
        self._decks[character].append(card)

        self._record_event("CARD_PICKED", character, {
            "card_id": card_id,
            "card_name": card_name,
            "variant": variant,
            "source": source,
            "new_deck_size": len(self._decks[character]),
        })
        logger.info(f"[DeckState] '{card_name}' (+1) thêm vào deck {character}. Tổng bài: {len(self._decks[character])}")

    def record_card_removed(self, character: str, card_id: str, card_name: str = "") -> bool:
        """Record a card being removed from a character's deck."""
        deck = self._decks.get(character, [])
        for i, card in enumerate(deck):
            if card.card_id == card_id or (card_name and card.card_name.lower() == card_name.lower()):
                removed = deck.pop(i)
                self._record_event("CARD_REMOVED", character, {
                    "card_id": removed.card_id,
                    "card_name": removed.card_name,
                    "new_deck_size": len(deck),
                })
                logger.info(f"[DeckState] '{removed.card_name}' (-1) đã xóa khỏi deck {character}. Còn lại: {len(deck)}")
                return True

        # If card wasn't strictly found, still log the remove event
        self._record_event("CARD_REMOVED", character, {
            "card_id": card_id,
            "card_name": card_name,
            "note": "card_not_found_in_memory_deck",
            "new_deck_size": len(deck),
        })
        return False

    def record_card_upgraded(
        self,
        character: str,
        base_card_id: str,
        new_variant_id: str,
        variant_name: str
    ) -> bool:
        """Record an Epiphany / Fate upgrade replacing a base card."""
        deck = self._decks.get(character, [])
        for card in deck:
            if card.card_id == base_card_id:
                card.card_id = new_variant_id
                card.variant = variant_name
                self._record_event("CARD_UPGRADED", character, {
                    "base_card_id": base_card_id,
                    "new_variant_id": new_variant_id,
                    "variant_name": variant_name,
                })
                logger.info(f"[DeckState] Thẻ '{card.card_name}' nâng cấp thành [{variant_name}] ({new_variant_id})")
                return True

        self._record_event("CARD_UPGRADED", character, {
            "base_card_id": base_card_id,
            "new_variant_id": new_variant_id,
            "variant_name": variant_name,
            "note": "base_card_not_found_in_memory_deck",
        })
        return False

    def record_card_copied(self, character: str, card_id: str, card_name: str) -> None:
        """Record a card being duplicated."""
        if character not in self._decks:
            self._decks[character] = []

        card = DeckCard(card_id=card_id, card_name=card_name, character=character, is_copied=True)
        self._decks[character].append(card)

        self._record_event("CARD_COPIED", character, {
            "card_id": card_id,
            "card_name": card_name,
            "new_deck_size": len(self._decks[character]),
        })
        logger.info(f"[DeckState] Thẻ '{card_name}' (bản sao) thêm vào deck {character}. Tổng: {len(self._decks[character])}")

    def _record_event(self, event_type: str, character: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Record event to history and append to JSONL file."""
        event = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "epoch": time.time(),
            "run_id": self.run_id,
            "event": event_type,
            "character": character,
            "details": details or {},
        }
        self._history.append(event)

        try:
            os.makedirs(self.log_dir, exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"Could not append deck event to {self.log_file}: {e}")

