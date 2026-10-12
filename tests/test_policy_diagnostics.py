import json
from pathlib import Path
import tempfile
import unittest

from cedhai.policy_diagnostics import analyze_run, diagnose_evaluation
from tests.test_learning_data import episode, save_episode


class PolicyDiagnosticsTests(unittest.TestCase):
    def test_forced_choices_and_competing_land_casts_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            events = episode()
            events[0]["observation"]["legal_actions"] = [{"id": "pass"}]
            events[2]["observation"]["legal_actions"] = [{"id": "pass"}, {"id": "cast:0"}]
            events[4]["observation"]["legal_actions"].append({"id": "cast:0"})
            save_episode(path, events)
            seats = analyze_run(path)
            self.assertEqual(seats[0]["forced"], 1)
            self.assertEqual(seats[0]["cast_declined"], 1)
            self.assertEqual(seats[0]["cast_without_land_passes"], 0)
            self.assertEqual(seats[1]["cast_without_land_passes"], 1)
            report = {"policies": ["model", "defend", "defend", "defend"],
                      "games": [{"success": True, "run": str(path), "seat_to_profile": [1, 0, 2, 3]}]}
            target = path / "evaluation.json"
            target.write_text(json.dumps(report))
            diagnostic = diagnose_evaluation(target)
            self.assertEqual(diagnostic["profiles"][0]["counts"]["cast_without_land_passes"], 1)
            self.assertEqual(diagnostic["accepted_games"], 1)

    def test_unavailable_choice_and_inconsistent_outcome_are_rejected(self):
        for problem in ("choice", "outcome"):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp)
                events = episode()
                save_episode(path, events)
                if problem == "choice":
                    events[0]["response"]["action_id"] = "attack:999"
                else:
                    events.pop()
                (path / "trajectory.jsonl").write_text("\n".join(map(json.dumps, events)))
                with self.assertRaises(ValueError):
                    analyze_run(path)
