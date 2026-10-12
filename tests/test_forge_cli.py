import unittest

from cedhai.forge_cli import parse_results


class ForgeResultTests(unittest.TestCase):
    def test_win_preserves_seat_and_deck_name(self):
        result = parse_results(
            "startup\nGame Result: Game 1 ended in 1240 ms. Ai(3)-Feline Ferocity has won!\n"
        )
        self.assertEqual(result, [{
            "game": 1, "winner": "Ai(3)-Feline Ferocity", "draw": False,
            "duration_ms": 1240,
        }])

    def test_timeout_draw_and_missing_result(self):
        self.assertEqual(parse_results("Could not load deck - test"), [])
        result = parse_results("Game Result: Game 1 ended in a Draw! Took 120000 ms.\n")
        self.assertTrue(result[0]["draw"])
        self.assertIsNone(result[0]["winner"])
