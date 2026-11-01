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
    placeholder: bool = False  # slot known only by count, real card identity not observed yet


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

    def _placeholder(self, character: str, n: int) -> DeckCard:
        return DeckCard(
            card_id=f"unknown_{character.lower()}_{n}",
            card_name="",
            character=character,
            variant="Base",
            placeholder=True,
        )

    def _pop_placeholder(self, character: str) -> Optional[DeckCard]:
        deck = self._decks.get(character, [])
        for i in range(len(deck) - 1, -1, -1):
            if deck[i].placeholder:
                return deck.pop(i)
        return None

    @staticmethod
    def _base_name(name: str) -> str:
        """'Flicker Blade (Aegis)' -> 'flicker blade' (strip variant suffix, punctuation)."""
        n = re.sub(r"\(.*?\)", " ", (name or "").lower())
        return " ".join(re.sub(r"[^\w\s]", " ", n).split())

    def initialize_default_team(
        self,
        characters: List[str],
        default_starter_size: int = 7,
        card_rules: Optional[Dict[str, Any]] = None,  # kept for backward compatibility, unused
    ) -> None:
        """
        Create a deck of *placeholder* slots (count only, no invented card identities).
        Real cards replace placeholders when observed (reconcile_from_remove_screen) or
        picked/upgraded. Placeholders never count towards copy limits.
        """
        for char in characters:
            if char not in self._decks or len(self._decks[char]) == 0:
                self._decks[char] = [
                    self._placeholder(char, i + 1) for i in range(default_starter_size)
                ]
                self._record_event("INITIALIZE_DECK", char, details={
                    "initial_size": default_starter_size, "placeholder": True,
                })

    def sync_deck_size(self, character: str, target_size: int) -> None:
        """
        Synchronize in-memory deck count with the on-screen badge count.
        Grows with placeholders; shrinks by dropping placeholders first (real cards last).
        """
        if character not in self._decks:
            self._decks[character] = []
        deck = self._decks[character]
        current = len(deck)
        if current == target_size:
            return
        if current < target_size:
            for i in range(target_size - current):
                deck.append(self._placeholder(character, current + i + 1))
        else:
            for _ in range(current - target_size):
                if self._pop_placeholder(character) is None:
                    dropped = deck.pop()
                    logger.warning(
                        f"[DeckState] Badge={target_size} < bộ nhớ={current}: buộc bỏ thẻ thật '{dropped.card_name}'"
                    )
        self._record_event("SYNC_DECK_SIZE", character, details={"previous_size": current, "new_size": target_size})

    def reconcile_from_remove_screen(
        self,
        character: str,
        observed: List[Dict[str, str]],
        total_size: Optional[int] = None,
    ) -> None:
        """
        Replace the deck with cards actually seen on the Remove Card screen.
        observed: [{"card_id":..., "card_name":..., "variant":...}] (visible cards only).
        If the grid is scrollable and only part of the deck is visible, the remaining
        slots stay as placeholders so the total size is preserved.
        """
        if not observed:
            return
        size = max(total_size if total_size is not None else len(self._decks.get(character, [])), len(observed))
        real = [
            DeckCard(
                card_id=o.get("card_id", ""),
                card_name=o.get("card_name", ""),
                character=character,
                variant=o.get("variant", "Base") or "Base",
            )
            for o in observed
        ]
        rest = [self._placeholder(character, i + 1) for i in range(size - len(real))]
        self._decks[character] = real + rest
        self._record_event("RECONCILE_DECK", character, details={
            "observed": len(real), "placeholders": len(rest), "new_deck_size": len(self._decks[character]),
        })

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
            if c.placeholder:
                continue
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
        """
        Record a card removal. Matching is strict (exact id/name, then same base name).
        If the card is unknown, one *placeholder* slot is removed so the size stays correct;
        real cards are never dropped on a guess. Returns True only if a real card matched.
        """
        deck = self._decks.get(character, [])
        tid = (card_id or "").lower().strip()
        tname = (card_name or "").lower().strip()
        tbase = self._base_name(card_name)

        def _remove(i: int, note: str = "") -> None:
            removed = deck.pop(i)
            details = {"card_id": removed.card_id, "card_name": removed.card_name, "new_deck_size": len(deck)}
            if note:
                details["note"] = note
            self._record_event("CARD_REMOVED", character, details)
            logger.info(f"[DeckState] '{removed.card_name or removed.card_id}' (-1) khỏi deck {character}. Còn: {len(deck)}")

        # Pass 1: exact id / name
        for i, c in enumerate(deck):
            if c.placeholder:
                continue
            if (tid and c.card_id.lower() == tid) or (tname and c.card_name.lower() == tname):
                _remove(i)
                return True

        # Pass 2: same base name (ignores variant suffix, min length 4 to avoid junk matches)
        if len(tbase) >= 4:
            for i, c in enumerate(deck):
                if not c.placeholder and self._base_name(c.card_name) == tbase:
                    _remove(i)
                    return True

        # Not found: keep size in sync using a placeholder, never guess a real card
        ph = self._pop_placeholder(character)
        if ph is not None:
            self._record_event("CARD_REMOVED", character, {
                "card_id": card_id, "card_name": card_name,
                "note": "card_unknown_removed_placeholder", "new_deck_size": len(deck),
            })
            logger.warning(f"[DeckState] '{card_name}' chưa có trong bộ nhớ, trừ 1 slot placeholder ({character}).")
            return False

        self._record_event("CARD_REMOVED", character, {
            "card_id": card_id, "card_name": card_name,
            "note": "card_not_found_no_change", "new_deck_size": len(deck),
        })
        logger.warning(f"[DeckState] Không tìm thấy '{card_name}' để xóa trong deck {character}; giữ nguyên.")
        return False

    def record_card_upgraded(
        self,
        character: str,
        base_card_id: str = "",
        new_variant_id: str = "",
        variant_name: str = "",
        card_id: str = "",
        card_name: str = "",
        new_variant: str = "",
    ) -> bool:
        """
        Record an Epiphany/Fate upgrade. An upgrade REPLACES a card, deck size never changes.
        Resolution order: exact base id -> same base name -> convert one placeholder slot.
        If nothing matches, the deck is left untouched (no +1).
        """
        base_id = base_card_id or card_id
        variant_id = new_variant_id or card_id
        v_name = variant_name or new_variant or "Upgraded"
        tbase = self._base_name(card_name)
        deck = self._decks.get(character, [])

        def _apply(card: DeckCard, note: str = "") -> bool:
            card.card_id = variant_id or card.card_id
            if card_name:
                card.card_name = card_name
            card.variant = v_name
            card.placeholder = False
            details = {"base_card_id": base_id, "new_variant_id": variant_id, "variant_name": v_name,
                       "new_deck_size": len(deck)}
            if note:
                details["note"] = note
            self._record_event("CARD_UPGRADED", character, details)
            logger.info(f"[DeckState] Nâng cấp '{card.card_name}' -> [{v_name}] ({variant_id})")
            return True

        for card in deck:
            if not card.placeholder and base_id and card.card_id == base_id:
                return _apply(card)
        if len(tbase) >= 4:
            for card in deck:
                if not card.placeholder and self._base_name(card.card_name) == tbase:
                    return _apply(card)
        for card in deck:
            if card.placeholder:
                return _apply(card, note="converted_placeholder")

        self._record_event("CARD_UPGRADED", character, {
            "base_card_id": base_id, "new_variant_id": variant_id, "variant_name": v_name,
            "note": "base_card_not_found_no_change", "new_deck_size": len(deck),
        })
        logger.warning(f"[DeckState] Không tìm thấy thẻ gốc cho '{card_name}' ({character}); giữ nguyên deck.")
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

