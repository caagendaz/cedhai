"""Audit supplied Commander lists against a timestamped Scryfall snapshot."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.request
import urllib.error
import urllib.parse

from .decklist import Decklist, load_decklist


def fetch_cards(names: list[str]) -> dict:
    cards, missing = [], []
    def normalized(card, aliases=()):
        result = {key: card.get(key) for key in (
            "id", "oracle_id", "name", "scryfall_uri", "color_identity", "legalities",
            "type_line", "mana_cost", "cmc", "released_at", "set",
        )}
        result["card_faces"] = [{"name": face["name"]} for face in card.get("card_faces", [])]
        result["aliases"] = list(aliases)
        return result
    for start in range(0, len(names), 75):
        if start:
            time.sleep(0.12)
        request = urllib.request.Request(
            "https://api.scryfall.com/cards/collection",
            data=json.dumps({"identifiers": [{"name": name} for name in names[start:start + 75]]}).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/json",
                     "User-Agent": "cedhai/0.1 (Commander research prototype)"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
        for card in result["data"]:
            cards.append(normalized(card))
        missing.extend(item["name"] for item in result.get("not_found", []))
    # Named lookup can recognize alternate printed names that collection lookup misses.
    unresolved = []
    for name in missing:
        time.sleep(0.12)
        request = urllib.request.Request(
            "https://api.scryfall.com/cards/named?exact=" + urllib.parse.quote(name),
            headers={"Accept": "application/json", "User-Agent": "cedhai/0.1 (Commander research prototype)"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                cards.append(normalized(json.load(response), [name]))
        except urllib.error.HTTPError as ex:
            if ex.code != 404:
                raise
            unresolved.append(name)
    return {"schema_version": 1, "source": "https://api.scryfall.com/cards/collection",
            "checked_at": datetime.now(timezone.utc).isoformat(), "cards": cards, "not_found": unresolved}


def audit_deck(deck: Decklist, snapshot: dict) -> dict:
    lookup = {}
    for card in snapshot["cards"]:
        lookup[card["name"].casefold()] = card
        for alias in card.get("aliases", []):
            lookup[alias.casefold()] = card
        for face in card.get("card_faces") or []:
            lookup[face["name"].casefold()] = card
    playable = [entry for entry in deck.cards if entry.section in {"main", "commander"}]
    problems = []
    identity = set()
    commanders_known = bool(deck.commanders)
    for entry in deck.commanders:
        card = lookup.get(entry.name.casefold())
        if card is None:
            commanders_known = False
        else:
            identity.update(card["color_identity"])
    total = sum(entry.count for entry in playable)
    if total != 100:
        problems.append({"kind": "deck_size", "count": total})
    if not deck.commanders:
        problems.append({"kind": "missing_commander"})
    counts = Counter()
    newer = []
    aliases = []
    for entry in playable:
        card = lookup.get(entry.name.casefold())
        if card is None:
            problems.append({"kind": "unknown_card", "card": entry.name})
            continue
        canonical = card["oracle_id"] or card["id"]
        counts[canonical] += entry.count
        if card.get("released_at", "") > "2026-09-21":
            newer.append({"card": entry.name, "released_at": card["released_at"], "source": card["scryfall_uri"]})
        if card["name"] != entry.name and entry.name in card.get("aliases", []):
            aliases.append({"supplied_name": entry.name, "oracle_name": card["name"], "source": card["scryfall_uri"]})
        if commanders_known and not set(card["color_identity"]).issubset(identity):
            problems.append({"kind": "color_identity", "card": entry.name,
                             "card_colors": card["color_identity"], "source": card["scryfall_uri"]})
        legality = card["legalities"].get("commander", "unknown")
        if legality != "legal":
            problems.append({"kind": "commander_legality", "card": entry.name,
                             "status": legality, "source": card["scryfall_uri"]})
    # This is a conservative preflight. Card-specific singleton exceptions and
    # commander pairing/eligibility remain the rules engine validator's job.
    for canonical, count in counts.items():
        card = next(c for c in snapshot["cards"] if (c["oracle_id"] or c["id"]) == canonical)
        if count > 1 and "Basic" not in card["type_line"]:
            problems.append({"kind": "singleton_review", "card": card["name"], "count": count})
    return {"deck": deck.name, "playable_count": total,
            "sideboard_count": sum(c.count for c in deck.cards if c.section == "sideboard"),
            "commanders": [c.name for c in deck.commanders], "color_identity": sorted(identity),
            "preflight_passed": not problems, "issues": problems,
            "printing_newer_than_engine_release": newer, "printed_name_aliases": aliases,
            "engine_validation_required": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decks", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, help="Use a saved Scryfall snapshot offline")
    args = parser.parse_args()
    decks = [load_decklist(path) for path in args.decks]
    names = sorted({c.name for deck in decks for c in deck.cards})
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot else fetch_cards(names)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "scryfall.json").write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report = {"source": snapshot["source"], "checked_at": snapshot["checked_at"],
              "decks": [audit_deck(deck, snapshot) for deck in decks]}
    (args.out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
