"""
Deck State Tracker with In-Memory Count and JSONL Event Logging for Chaos Zero Nightmare.
Pure Python, zero-dependency Event Sourcing tracker per run.
"""
import os
import re
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

    def initialize_default_team(
        self,
        characters: List[str],
        default_starter_size: int = 7,
        card_rules: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Initialize sensible starter decks for characters if not already initialized.
        In Chaos Zero Nightmare, starting combatants begin with ~7-8 starter cards.
        """
        for char in characters:
            if char not in self._decks or len(self._decks[char]) == 0:
                starter_cards = []
                char_lower = char.lower()

                # Look for real starter cards from card_rules if available
                attack_card = None
                skill_card = None
                if card_rules and "cards" in card_rules:
                    for c in card_rules["cards"]:
                        if c.get("character", "").lower() == char_lower:
                            ctype = c.get("type", "")
                            if ctype == "Basic Attack" and not attack_card:
                                attack_card = c
                            elif ctype == "Basic Skill" and not skill_card:
                                skill_card = c

                atk_id = attack_card.get("id") if attack_card else f"{char_lower}_basic_attack_base"
                atk_name = attack_card.get("name") if attack_card else "Basic Attack"
                skl_id = skill_card.get("id") if skill_card else f"{char_lower}_basic_skill_base"
                skl_name = skill_card.get("name") if skill_card else "Basic Skill"

                for i in range(4):
                    starter_cards.append(DeckCard(
                        card_id=atk_id,
                        card_name=atk_name,
                        character=char,
                        variant="Base"
                    ))
                for i in range(2):
                    starter_cards.append(DeckCard(
                        card_id=skl_id,
                        card_name=skl_name,
                        character=char,
                        variant="Base"
                    ))
                if default_starter_size > 6:
                    starter_cards.append(DeckCard(
                        card_id=f"{char_lower}_starter_special",
                        card_name="Special Starter",
                        character=char,
                        variant="Base"
                    ))
                self._decks[char] = starter_cards
                self._record_event("INITIALIZE_DECK", char, details={"initial_size": len(starter_cards)})

    def sync_deck_size(self, character: str, target_size: int) -> None:
        """
        Synchronize in-memory deck count with observed on-screen badge count.
        """
        if character not in self._decks:
            self._decks[character] = []
        current = len(self._decks[character])
        if current == target_size:
            return
        if current < target_size:
            for i in range(target_size - current):
                self._decks[character].append(DeckCard(
                    card_id=f"{character.lower()}_synced_card_{i+1}",
                    card_name="Synced Card",
                    character=character,
                    variant="Base"
                ))
        else:
            self._decks[character] = self._decks[character][:target_size]
        self._record_event("SYNC_DECK_SIZE", character, details={"previous_size": current, "new_size": target_size})

    def get_deck(self, character: str) -> List[DeckCard]:
        return list(self._decks.get(character, []))

    def get_deck_size(self, character: str) -> int:
        return len(self._decks.get(character, []))

    def get_total_deck_size(self) -> int:
        return sum(len(deck) for deck in self._decks.values())

    def count_copies(self, character: str, card_id: str, include_variants: bool = False) -> int:
        if not card_id:
            return 0
        cid_lower = card_id.lower().strip()
        cid_norm = cid_lower.replace("_", " ")
        count = 0
        for c in self._decks.get(character, []):
            c_id = c.card_id.lower()
            c_name = c.card_name.lower() if c.card_name else ""

            if c_id == cid_lower or (c_name and c_name == cid_lower):
                count += 1
            elif not include_variants:
                if cid_norm == c_id.replace("_", " ") or (c_name and cid_norm == c_name.replace("_", " ")):
                    count += 1
            else:
                c_id_norm = c_id.replace("_", " ")
                c_name_norm = c_name.replace("_", " ")
                if (
                    cid_lower in c_id
                    or c_id in cid_lower
                    or (c_name and (cid_lower in c_name or c_name in cid_lower))
                    or (cid_norm in c_id_norm or c_id_norm in cid_norm)
                ):
                    count += 1
                else:
                    tokens = set(re.findall(r"[a-z0-9]+", cid_norm)) - {
                        "base", "skill", "attack", "rossweisse", "tiphera", "nia", "chizuru",
                        "diana", "dingo", "haru", "hilde", "rin", "sereniel", "curse", "season"
                    }
                    c_tokens = set(re.findall(r"[a-z0-9]+", c_id_norm + " " + c_name_norm)) - {
                        "base", "skill", "attack", "rossweisse", "tiphera", "nia", "chizuru",
                        "diana", "dingo", "haru", "hilde", "rin", "sereniel", "curse", "season"
                    }
                    if tokens and c_tokens and (tokens.issubset(c_tokens) or c_tokens.issubset(tokens)):
                        count += 1
        return count

    def has_card(self, character: str, card_id: str) -> bool:
        return self.count_copies(character, card_id, include_variants=False) > 0

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
        target_id_lower = card_id.lower().strip() if card_id else ""
        target_name_lower = card_name.lower().strip() if card_name else ""

        # Pass 1: Exact match on card_id or card_name
        for i, card in enumerate(deck):
            c_id = card.card_id.lower()
            c_name = card.card_name.lower()
            if (target_id_lower and c_id == target_id_lower) or (target_name_lower and c_name == target_name_lower):
                removed = deck.pop(i)
                self._record_event("CARD_REMOVED", character, {
                    "card_id": removed.card_id,
                    "card_name": removed.card_name,
                    "new_deck_size": len(deck),
                })
                logger.info(f"[DeckState] '{removed.card_name}' (-1) đã xóa khỏi deck {character}. Còn lại: {len(deck)}")
                return True

        # Pass 2: Substring or normalized match
        for i, card in enumerate(deck):
            c_id = card.card_id.lower()
            c_name = card.card_name.lower()
            if (target_name_lower and (target_name_lower in c_name or c_name in target_name_lower or target_name_lower in c_id)) or \
               (target_id_lower and (target_id_lower in c_id or c_id in target_id_lower)):
                removed = deck.pop(i)
                self._record_event("CARD_REMOVED", character, {
                    "card_id": removed.card_id,
                    "card_name": removed.card_name,
                    "new_deck_size": len(deck),
                })
                logger.info(f"[DeckState] '{removed.card_name}' (-1) đã xóa khỏi deck {character}. Còn lại: {len(deck)}")
                return True

        # Pass 3: Starter basic fallback
        basic_terms = ["basic attack", "sword slash", "matter disintegration", "stroke", "standing blade", "barrier deployment", "basic skill"]
        is_basic = any(term in target_name_lower or term in target_id_lower for term in basic_terms)
        if is_basic:
            for i, card in enumerate(deck):
                c_name = card.card_name.lower()
                c_id = card.card_id.lower()
                if any(term in c_name or term in c_id for term in basic_terms):
                    removed = deck.pop(i)
                    self._record_event("CARD_REMOVED", character, {
                        "card_id": removed.card_id,
                        "card_name": removed.card_name,
                        "new_deck_size": len(deck),
                    })
                    logger.info(f"[DeckState] '{removed.card_name}' (-1) đã xóa khỏi deck {character}. Còn lại: {len(deck)}")
                    return True

        # Pass 4: Fallback to maintain synchronized deck size if deck is non-empty
        if deck:
            removed = None
            for i, card in enumerate(deck):
                c_name = card.card_name.lower()
                c_id = card.card_id.lower()
                if any(term in c_name or term in c_id for term in ["basic", "slash", "starter", "synced"]):
                    removed = deck.pop(i)
                    break
            if removed is None:
                removed = deck.pop()
            self._record_event("CARD_REMOVED", character, {
                "card_id": removed.card_id,
                "card_name": removed.card_name,
                "requested_id": card_id,
                "requested_name": card_name,
                "note": "fallback_removed_starter_to_keep_deck_synced",
                "new_deck_size": len(deck),
            })
            logger.info(f"[DeckState] '{removed.card_name}' (-1, fallback sync) đã xóa khỏi deck {character}. Còn lại: {len(deck)}")
            return True

        # If deck was completely empty
        self._record_event("CARD_REMOVED", character, {
            "card_id": card_id,
            "card_name": card_name,
            "note": "deck_was_empty",
            "new_deck_size": len(deck),
        })
        return False

    def record_card_upgraded(
        self,
        character: str,
        base_card_id: str = "",
        new_variant_id: str = "",
        variant_name: str = "",
        card_id: str = "",
        card_name: str = "",
        new_variant: str = ""
    ) -> bool:
        """Record an Epiphany / Fate upgrade replacing a base card."""
        base_id = base_card_id or card_id
        variant_id = new_variant_id or card_id
        v_name = variant_name or new_variant or "Upgraded"

        deck = self._decks.get(character, [])
        for card in deck:
            if card.card_id == base_id or (card_name and card.card_name.lower() in card_name.lower()):
                card.card_id = variant_id
                card.variant = v_name
                self._record_event("CARD_UPGRADED", character, {
                    "base_card_id": base_id,
                    "new_variant_id": variant_id,
                    "variant_name": v_name,
                })
                logger.info(f"[DeckState] Thẻ '{card.card_name}' nâng cấp thành [{v_name}] ({variant_id})")
                return True

        # If base card not found in memory deck, still add the upgraded card via record_card_picked
        self._record_event("CARD_UPGRADED", character, {
            "base_card_id": base_id,
            "new_variant_id": variant_id,
            "variant_name": v_name,
            "note": "base_card_not_found_fallback_added_to_deck",
        })
        self.record_card_picked(
            character=character,
            card_id=variant_id,
            card_name=card_name or v_name,
            variant=v_name,
            source="epiphany_upgrade"
        )
        return True

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

