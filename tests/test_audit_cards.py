import unittest

from cedhai.audit_cards import audit_deck
from cedhai.decklist import CardEntry, Decklist


def card(name, colors, type_line="Creature", legality="legal"):
    return {"id": name, "oracle_id": name, "name": name, "color_identity": colors,
            "type_line": type_line, "legalities": {"commander": legality},
            "scryfall_uri": "https://scryfall.com/card/example", "card_faces": None}


class CardAuditTests(unittest.TestCase):
    def test_printed_alias_resolves_without_changing_supplied_name(self):
        actual = card("Actual Name", ["U"])
        actual["aliases"] = ["Printed Name"]
        deck = Decklist("test", (CardEntry("Leader", 1, "commander"), CardEntry("Printed Name")))
        report = audit_deck(deck, {"cards": [card("Leader", ["U"]), actual]})
        self.assertEqual(report["printed_name_aliases"][0]["supplied_name"], "Printed Name")
        self.assertNotIn("unknown_card", [issue["kind"] for issue in report["issues"]])
    def test_off_color_unknown_and_banned_cards_remain_explicit(self):
        deck = Decklist("test", (CardEntry("Leader", 1, "commander"), CardEntry("Off color"),
                                CardEntry("Missing"), CardEntry("Banned")))
        result = audit_deck(deck, {"cards": [card("Leader", ["U", "B"]),
                              card("Off color", ["R", "G"]), card("Banned", [], legality="banned")]})
        self.assertEqual({x["kind"] for x in result["issues"]},
                         {"deck_size", "color_identity", "unknown_card", "commander_legality"})
        self.assertFalse(result["preflight_passed"])

    def test_basic_land_copies_and_sideboards_are_handled(self):
        deck = Decklist("test", (CardEntry("Leader", 1, "commander"), CardEntry("Island", 99),
                                CardEntry("Off color", 1, "sideboard")))
        result = audit_deck(deck, {"cards": [card("Leader", ["U"]),
                              card("Island", ["U"], "Basic Land - Island"), card("Off color", ["R"])]})
        self.assertTrue(result["preflight_passed"])
        self.assertEqual(result["sideboard_count"], 1)
        self.assertTrue(result["engine_validation_required"])
