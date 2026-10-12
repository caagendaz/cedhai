"""Opt-in real-engine test: set CEDHAI_TEST_XMAGE=1 before unittest discovery."""

import json
import os
import unittest
import uuid

from cedhai.forge_cli import PRECONS
from cedhai.run_bridge import ROOT, run_bridge


@unittest.skipUnless(os.environ.get("CEDHAI_TEST_XMAGE") == "1", "opt-in XMage integration test")
class XMageIntegrationTests(unittest.TestCase):
    def test_combat_eliminates_players_and_produces_true_rewards(self):
        jdk = next((ROOT / "tools/jdk").glob("jdk-*"))
        deck = ROOT / "examples/decks/curriculum/yargle.txt"
        out = ROOT / "runs" / ("combat-integration-" + uuid.uuid4().hex[:12])
        result = run_bridge(jdk, ROOT / "tools/magezero/xmage", [deck] * 4, out, 7, "develop", 100, 300, "basic")
        self.assertTrue(result["success"], result)
        self.assertGreater(result["attacks"], 0)
        finished = result["completion"]
        self.assertTrue(finished["terminal"])
        self.assertFalse(finished["truncated"])
        self.assertEqual(sum(finished["rewards"]), 1.0)
        self.assertEqual(len(finished["winners"]), 1)
        self.assertEqual([p["seat"] for p in finished["public_state"]["players"] if p["has_won"]], finished["winners"])
        self.assertFalse(any(p["in_game"] for p in finished["public_state"]["players"]))
        events = [json.loads(line) for line in (out / "trajectory.jsonl").read_text().splitlines()]
        self.assertTrue(any(any(max(c["damage_to_seats"]) > 0 for c in event["observation"]["public_state"]["commanders"])
                            for event in events if event["event"] == "decision"))

    def test_blocker_choices_are_applied(self):
        jdk = next((ROOT / "tools/jdk").glob("jdk-*"))
        deck = ROOT / "examples/decks/curriculum/isamaru.txt"
        out = ROOT / "runs" / ("blocking-integration-" + uuid.uuid4().hex[:12])
        result = run_bridge(jdk, ROOT / "tools/magezero/xmage", [deck] * 4, out, 7, "defend", 12, 300, "basic")
        self.assertTrue(result["success"], result)
        self.assertGreater(result["blocks"], 0)

    def test_python_casts_are_paid_and_resolve(self):
        jdk = next((ROOT / "tools/jdk").glob("jdk-*"))
        deck = ROOT / "examples/decks/curriculum/isamaru.txt"
        out = ROOT / "runs" / ("casting-integration-" + uuid.uuid4().hex[:12])
        result = run_bridge(jdk, ROOT / "tools/magezero/xmage", [deck] * 4, out, 7, "develop", 4, 300, "basic")
        self.assertTrue(result["success"], result)
        self.assertEqual(result["cast_spells"], 4)
        self.assertEqual(result["resolved_spells"], 4)
        events = [json.loads(line) for line in (out / "trajectory.jsonl").read_text().splitlines()]
        casts = [event for event in events if event["event"] == "applied" and event["action_id"].startswith("cast:")]
        self.assertEqual({event["seat"] for event in casts}, {0, 1, 2, 3})
        for cast in casts:
            self.assertEqual(cast["zone"], "STACK")
            self.assertTrue(cast["public_state"]["stack"])
            lands = [p for p in cast["public_state"]["battlefield"] if p["controller_seat"] == cast["seat"]]
            self.assertTrue(any(p["name"] == "Plains" and p["tapped"] for p in lands))

    def test_four_player_decisions_are_applied_and_private_hands_are_scoped(self):
        jdk = next((ROOT / "tools/jdk").glob("jdk-*"))
        decks = [ROOT / "tools/forge/res/adventure/Realm of Legends/decks/starter/commanderprecon" / name
                 for name in PRECONS]
        out = ROOT / "runs" / ("bridge-integration-" + uuid.uuid4().hex[:12])
        result = run_bridge(jdk, ROOT / "tools/magezero/xmage", decks, out, 7, "random", 4, 300)
        self.assertTrue(result["success"], result)
        self.assertGreater(result["applied_lands"], 0)
        events = [json.loads(line) for line in (out / "trajectory.jsonl").read_text().splitlines()]
        self.assertTrue(events[-1]["truncated"])
        self.assertFalse(events[-1]["terminal"])
        observed_seats = set()
        turns = {}
        for index, event in enumerate(events[:-1]):
            if event["event"] != "decision":
                continue
            observation = event["observation"]
            observed_seats.add(observation["seat"])
            state = observation["public_state"]
            turns[state["turn"]] = state["active_seat"]
            self.assertEqual(len(state["players"]), 4)
            # Opponents expose public counts, never hands or library identities.
            for player in state["players"]:
                self.assertEqual(set(player), {"seat", "life", "hand_count", "library_count", "battlefield_count", "in_game", "mana_pool", "has_won", "has_lost", "has_drawn"})
            self.assertEqual(set(observation["private_state"]), {"hand"})
            actor = state["players"][observation["seat"]]
            self.assertEqual(len(observation["private_state"]["hand"]), actor["hand_count"])
            application = events[index + 1]
            self.assertEqual(application["event"], "applied")
            self.assertEqual(application["request_id"], event["request_id"])
            self.assertEqual(application["action_id"], event["response"]["action_id"])
            self.assertIn(application["action_id"], [a["id"] for a in observation["legal_actions"]])
            if application["action_id"].startswith("land:"):
                before = state["players"][observation["seat"]]["battlefield_count"]
                after = application["public_state"]["players"][observation["seat"]]["battlefield_count"]
                self.assertEqual(application["zone"], "BATTLEFIELD")
                self.assertGreaterEqual(after, before + 1)
        self.assertEqual(observed_seats, {0, 1, 2, 3})
        self.assertEqual(turns, {1: 0, 2: 1, 3: 2, 4: 3})
