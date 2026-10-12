from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cedhai.decklist import load_decklist


class DecklistTests(unittest.TestCase):
    def test_loads_counted_commander_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.txt"
            path.write_text(
                "\n".join(
                    [
                        "Commander",
                        "1 Rograkh, Son of Rohgahh",
                        "1 Silas Renn, Seeker Adept",
                        "",
                        "Deck",
                        "1 Sol Ring",
                        "2 Island (ABC) 123",
                        "// ignored",
                    ]
                ),
                encoding="utf-8",
            )

            deck = load_decklist(path)

        self.assertEqual(deck.name, "sample")
        self.assertEqual(deck.total_cards, 5)
        self.assertEqual([card.name for card in deck.commanders], ["Rograkh, Son of Rohgahh", "Silas Renn, Seeker Adept"])
        self.assertIn("Island", [card.name for card in deck.cards])

    def test_rejects_empty_decklist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.txt"
            path.write_text("# no cards", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_decklist(path)


if __name__ == "__main__":
    unittest.main()
