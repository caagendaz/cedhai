from pathlib import Path
import unittest

from cedhai.decklist import load_decklist
from cedhai.run_bridge import export_xmage_deck


ROOT = Path(__file__).resolve().parents[1]


class ReferenceDeckTests(unittest.TestCase):
    def test_all_reference_decks_have_100_playable_cards(self):
        for path in (ROOT / "examples/decks/reference").glob("*.txt"):
            with self.subTest(deck=path.stem):
                deck = load_decklist(path)
                self.assertEqual(sum(c.count for c in deck.cards if c.section in {"main", "commander"}), 100)

    def test_winota_sideboard_is_preserved_and_excluded_from_export(self):
        path = ROOT / "examples/decks/reference/winota.txt"
        deck = load_decklist(path)
        self.assertEqual([c.name for c in deck.commanders], ["Winota, Joiner of Forces"])
        self.assertEqual([c.name for c in deck.cards if c.section == "sideboard"], ["Alexios, Deimos of Kosmos"])
        self.assertNotIn("Alexios", export_xmage_deck(path))

    def test_yuriko_is_preserved_without_silent_substitutions(self):
        deck = load_decklist(ROOT / "examples/decks/reference/yuriko.txt")
        self.assertEqual([c.name for c in deck.commanders], ["Yuriko, the Tiger's Shadow"])
        self.assertIn("Samut, Tyrant of Naktamun", [c.name for c in deck.cards])
        self.assertIn("Lim-Dûl's Vault", [c.name for c in deck.cards])
