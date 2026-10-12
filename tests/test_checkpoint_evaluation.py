import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cedhai.agents import BaselineAgent
from cedhai.decision_bridge import DecisionSession
from cedhai.engine import Action, Observation
from cedhai.evaluate import decision_counts, seating_plan, summarize, validate_experiment
from tests.test_learning_data import observation


class CheckpointEvaluationTests(unittest.TestCase):
    def test_checkpoint_cli_passes_external_agents_and_valid_bridge_labels(self):
        import importlib.util
        if not importlib.util.find_spec("torch"):
            self.skipTest("optional PyTorch dependency")
        from cedhai.evaluate import main
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkpoint = root / "checkpoint.pt"
            checkpoint.write_bytes(b"mock checkpoint")
            class Model:
                def __init__(self, path):
                    self.checkpoint = {"dataset_sha256": "test", "epoch": 5}
            completion = {"terminal": True, "truncated": False, "winners": [0]}
            argv = ["evaluate", "--checkpoint", str(checkpoint), "--policies", "model", "defend", "defend", "defend",
                    "--seeds", "13", "--out", str(root / "evaluation")]
            with patch("sys.argv", argv), patch("cedhai.model.ModelAgent", Model), \
                 patch("cedhai.evaluate.run_bridge", return_value={"success": True, "completion": completion, "decisions": 1}) as bridge, \
                 patch("cedhai.evaluate.decision_counts", return_value=[]), patch("builtins.print"):
                main()
            self.assertEqual(bridge.call_count, 4)
            for call in bridge.call_args_list:
                self.assertNotIn("model", call.args[9])
                self.assertEqual(sum(isinstance(agent, Model) for agent in call.args[10]), 1)
            target = root / "evaluation/evaluation.json"
            report = json.loads(target.read_text())
            report["games"].pop()
            target.write_text(json.dumps(report))
            (root / "evaluation/seed13-rotation3").mkdir()
            with patch("sys.argv", argv + ["--resume"]), patch("cedhai.model.ModelAgent", Model), \
                 patch("cedhai.evaluate.run_bridge", return_value={"success": True, "completion": completion, "decisions": 1}) as bridge, \
                 patch("cedhai.evaluate.decision_counts", return_value=[]), patch("builtins.print"):
                main()
            self.assertEqual(bridge.call_count, 1)
            self.assertTrue(str(bridge.call_args.args[3]).endswith("attempt2"))
            with patch("sys.argv", argv + ["--resume", "--turns", "50"]), patch("cedhai.model.ModelAgent", Model):
                with self.assertRaisesRegex(ValueError, "Resume experiment differs"):
                    main()
    def test_checkpoint_and_declared_development_seeds_are_validated(self):
        validate_experiment([13, 14], [7, 10, 11, 12], ["model", "defend", "defend", "defend"], Path("model.pt"))
        for seeds, checkpoint, policies in (([7], Path("x"), ["model"] * 4),
                                             ([13], None, ["model"] * 4),
                                             ([13], Path("x"), ["defend"] * 4)):
            with self.assertRaises(ValueError):
                validate_experiment(seeds, [7], policies, checkpoint)

    def test_seat_accounting_duplicates_and_unfinished_games(self):
        games = [{**item, "success": True, "terminal": True, "truncated": False, "winners": [0]}
                 for item in seating_plan([13])]
        result = summarize(games, ["model", "defend", "defend", "defend"])
        self.assertEqual([row["completed"] for row in result["profiles"][0]["seats"]], [1] * 4)
        self.assertEqual([row["wins"] for row in result["profiles"][0]["seats"]], [1, 0, 0, 0])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            summarize(games + games[:1], ["defend"] * 4)
        unfinished = {**games[0], "terminal": False}
        self.assertEqual(summarize([unfinished], ["defend"] * 4)["profiles"][0]["errors"], 1)

    def test_external_baselines_match_bridge_controls(self):
        for policy in ("pass", "random", "land", "develop", "defend"):
            data = observation()
            data["legal_actions"].append({"id": "cast:0", "label": "Cast"})
            event = {"schema_version": 2, "event": "decision", "request_id": "xmage-7:0",
                     "scope": "priority_basic", "observation": data}
            expected = DecisionSession(io.StringIO(), 7, policy=policy).handle(event)["action_id"]
            obs = Observation(**{**data, "legal_actions": tuple(Action(**a) for a in data["legal_actions"]),
                                  "decision_type": "priority_basic"})
            self.assertEqual(BaselineAgent(7, policy).choose_action(obs).id, expected)
        obs = Observation("g", 0, 0, {}, {}, (Action("skip", "Skip"), Action("block:0", "Block")), "block")
        self.assertEqual(BaselineAgent(0, "develop").choose_action(obs).id, "skip")
        self.assertEqual(BaselineAgent(0, "defend").choose_action(obs).id, "block:0")

    def test_decision_diagnostics_exclude_forced_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = []
            for legal in ([{"id": "pass"}], [{"id": "skip"}, {"id": "attack:1"}]):
                events.append({"event": "decision", "scope": "attack" if len(legal) > 1 else "priority_basic",
                               "observation": {"seat": 0, "legal_actions": legal},
                               "response": {"action_id": legal[-1]["id"]}})
            (Path(tmp) / "trajectory.jsonl").write_text("\n".join(map(json.dumps, events)))
            result = decision_counts(Path(tmp))[0]
            self.assertEqual(result["decisions"], 2)
            self.assertEqual(result["choices"], 1)
            self.assertEqual(result["selected"], {"attack": 1})
