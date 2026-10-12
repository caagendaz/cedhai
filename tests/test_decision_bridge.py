from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

from cedhai.decision_bridge import DecisionSession
from cedhai.run_bridge import export_xmage_deck


def decision():
    return {
        "event": "decision", "schema_version": 1, "request_id": "xmage-7:0",
        "scope": "own_hand_land_or_pass", "observation": {
            "game_id": "xmage-7", "step": 0, "seat": 0,
            "public_state": {"turn": 1, "active_seat": 0},
            "private_state": {"hand": [{"id": "card1", "name": "Forest"}]},
            "legal_actions": [{"id": "pass", "label": "Pass priority"},
                              {"id": "land:0", "label": "Play Forest"}],
        },
    }


def applied(action_id="land:0"):
    return {"event": "applied", "schema_version": 1, "request_id": "xmage-7:0",
            "action_id": action_id, "seat": 0, "zone": "BATTLEFIELD"}


class DecisionBridgeTests(unittest.TestCase):
    def test_combat_choices_and_terminal_rewards_are_verified(self):
        session = DecisionSession(io.StringIO(), 7, "develop")
        event = decision()
        event.update(schema_version=2, scope="attack")
        event["observation"]["legal_actions"] = [{"id": "skip", "label": "Skip"},
                                                 {"id": "attack:1", "label": "Attack seat 1"}]
        self.assertEqual(session.handle(event)["action_id"], "attack:1")
        application = applied("attack:1")
        application["schema_version"] = 2
        session.handle(application)
        self.assertEqual(session.attacks, 1)
        finished = {"event": "finished", "schema_version": 2, "game_id": "xmage-7",
                    "decisions": 1, "applied_lands": 0, "cast_spells": 0, "resolved_spells": 0,
                    "attacks": 1, "blocks": 0, "terminal": True, "truncated": False,
                    "winners": [0], "rewards": [0.0] * 4}
        with self.assertRaisesRegex(ValueError, "Rewards"):
            session.handle(finished)
        finished["rewards"] = [1.0, 0.0, 0.0, 0.0]
        session.handle(finished)

    def test_cast_application_and_resolution_are_distinct(self):
        session = DecisionSession(io.StringIO(), 7, "develop")
        event = decision()
        event.update(schema_version=2, scope="priority_basic")
        event["observation"]["legal_actions"][1] = {"id": "cast:0", "label": "Cast creature"}
        self.assertEqual(session.handle(event)["action_id"], "cast:0")
        cast = applied("cast:0")
        cast.update(schema_version=2, zone="STACK", card_id="creature")
        session.handle(cast)
        self.assertEqual(session.cast_spells, 1)
        self.assertEqual(session.resolved_spells, 0)
        resolution = {"event": "resolved", "schema_version": 2, "request_id": "xmage-7:0",
                      "card_id": "creature", "zone": "BATTLEFIELD"}
        session.handle(resolution)
        self.assertEqual(session.resolved_spells, 1)
        with self.assertRaisesRegex(ValueError, "Unknown"):
            session.handle(resolution)

    def test_choice_application_and_truncation_are_recorded_separately(self):
        writer = io.StringIO()
        session = DecisionSession(writer, 7, "land")
        request = decision()
        self.assertEqual(session.handle(request)["action_id"], "land:0")
        self.assertEqual(session.applied_lands, 0)
        session.handle(applied())
        self.assertEqual(session.applied_lands, 1)
        session.handle({"event": "finished", "schema_version": 1, "game_id": "xmage-7",
                        "decisions": 1, "applied_lands": 1, "terminal": False, "truncated": True})
        records = [json.loads(line) for line in writer.getvalue().splitlines()]
        self.assertEqual([item["event"] for item in records], ["decision", "applied", "finished"])
        self.assertEqual(request, decision())
        with self.assertRaisesRegex(ValueError, "already finished"):
            session.handle(decision())

    def test_stale_or_unapplied_choices_are_rejected(self):
        session = DecisionSession(io.StringIO(), 7, "land")
        session.handle(decision())
        with self.assertRaisesRegex(ValueError, "not been applied"):
            session.handle(decision())
        with self.assertRaisesRegex(ValueError, "does not match"):
            session.handle(applied("pass"))
        event = applied()
        event["zone"] = "HAND"
        with self.assertRaisesRegex(ValueError, "battlefield"):
            session.handle(event)
        self.assertEqual(session.applied_lands, 0)

    def test_invalid_actor_or_duplicate_actions_are_rejected(self):
        for field, value in (("seat", 4), ("seat", True), ("step", 1)):
            event = deepcopy(decision())
            event["observation"][field] = value
            with self.assertRaises(ValueError):
                DecisionSession(io.StringIO(), 7).handle(event)
        event = decision()
        event["observation"]["legal_actions"].append({"id": "pass", "label": "Duplicate"})
        with self.assertRaisesRegex(ValueError, "duplicate"):
            DecisionSession(io.StringIO(), 7).handle(event)

    def test_random_policy_is_seeded_and_selects_only_available_actions(self):
        choices = []
        for _ in range(2):
            session = DecisionSession(io.StringIO(), 17)
            choices.append(session.handle(decision())["action_id"])
        self.assertEqual(choices[0], choices[1])
        self.assertIn(choices[0], {"pass", "land:0"})
        session = DecisionSession(io.StringIO(), 7, "pass")
        self.assertEqual(session.handle(decision())["action_id"], "pass")

    def test_forge_export_moves_commander_to_xmage_sideboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.dck"
            path.write_text("[metadata]\nName=Test\n[Commander]\n1 Kinnan, Bonder Prodigy+|IKO\n"
                            "[Main]\n40 Forest|M21\n59 Island|M21\n", encoding="utf-8")
            self.assertEqual(export_xmage_deck(path),
                             "40 Forest\n59 Island\n//sideboard\n1 Kinnan, Bonder Prodigy\n")

    def test_unknown_sections_are_not_silently_imported_as_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.dck"
            path.write_text("[Main]\n1 Forest\n[Sideboard]\n1 Island\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unsupported Forge section"):
                export_xmage_deck(path)


if __name__ == "__main__":
    unittest.main()
