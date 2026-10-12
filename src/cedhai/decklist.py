from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


_COUNTED_LINE = re.compile(r"^\s*(?P<count>\d+)x?\s+(?P<name>.+?)\s*$")
_SECTION_HEADERS = {
    "commander",
    "commanders",
    "main",
    "maindeck",
    "deck",
    "sideboard",
    "companions",
}


@dataclass(frozen=True)
class CardEntry:
    name: str
    count: int = 1
    section: str = "main"


@dataclass(frozen=True)
class Decklist:
    name: str
    cards: tuple[CardEntry, ...]

    @property
    def total_cards(self) -> int:
        return sum(card.count for card in self.cards)

    @property
    def commanders(self) -> tuple[CardEntry, ...]:
        return tuple(card for card in self.cards if card.section == "commander")


def load_decklist(path: str | Path) -> Decklist:
    deck_path = Path(path)
    cards: list[CardEntry] = []
    section = "main"

    for raw_line in deck_path.read_text(encoding="utf-8").splitlines():
        line = _strip_comment(raw_line)
        if not line:
            continue

        normalized = line.strip().lower().rstrip(":")
        if normalized in _SECTION_HEADERS:
            section = "commander" if normalized in {"commander", "commanders"} else "main"
            continue

        match = _COUNTED_LINE.match(line)
        if match:
            count = int(match.group("count"))
            name = _clean_card_name(match.group("name"))
        else:
            count = 1
            name = _clean_card_name(line)

        if not name:
            continue
        cards.append(CardEntry(name=name, count=count, section=section))

    if not cards:
        raise ValueError(f"Decklist has no cards: {deck_path}")

    return Decklist(name=deck_path.stem, cards=tuple(cards))


def _strip_comment(line: str) -> str:
    for marker in ("//", "#"):
        if marker in line:
            line = line.split(marker, 1)[0]
    return line.strip()


def _clean_card_name(name: str) -> str:
    name = re.sub(r"\s+\([A-Z0-9]{2,}\)\s+\d+\s*$", "", name.strip())
    return name.strip()
