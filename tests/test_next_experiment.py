from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import signal
import zipfile

from cedhai.compare_results import compare
from cedhai.evaluate import seating_plan, summarize
from cedhai.next_experiment import COLLECTION_SEEDS, DEVELOPMENT_SEEDS, EVALUATION_SEEDS, REFERENCE_HASH, experiment, fresh_path, require_complete, stop_process_group
from tests.test_review_results import documents


def archive(path, candidate=False):
    evaluation, diagnostics = documents()
    evaluation["experiment"].update(turns=100, timeout=300, deck_sha256="c" * 64, bridge_sha256="d" * 64)
    if candidate:
        evaluation["checkpoint"]["sha256"] = "e" * 64
        evaluation["experiment"]["checkpoint"] = deepcopy(evaluation["checkpoint"])
        for game in evaluation["games"]:
            game["winners"] = [game["seat_to_profile"].index(0)]
        evaluation["summary"] = summarize(evaluation["games"], evaluation["policies"])
    with zipfile.ZipFile(path, "w") as writer:
        writer.writestr("evaluation.json", json.dumps(evaluation))
        writer.writestr("diagnostics.json", json.dumps(diagnostics))
    return evaluation, diagnostics


class NextExperimentTests(unittest.TestCase):
    def test_interruption_stops_the_module_process_group(self):
        process = Mock(pid=123)
        with patch("cedhai.next_experiment.os.killpg", create=True) as kill:
            stop_process_group(process)
        kill.assert_called_once_with(123, signal.SIGTERM)
        process.wait.assert_called_once_with(timeout=10)

    def test_notebook_code_and_stage_order(self):
        path = Path(__file__).resolve().parents[1] / "notebooks/colab_next_experiment.ipynb"
        codes = ["".join(cell["source"]) for cell in json.loads(path.read_text())["cells"] if cell["cell_type"] == "code"]
        for source in codes:
            compile(source, str(path), "exec")
        self.assertEqual([source.splitlines()[0] for source in codes if source.startswith("stage(")],
                         ["stage('collect')", "stage('train')", "stage('evaluate')", "stage('export')"])
    def test_collection_resume_and_changed_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference = root / "input.pt"
            reference.write_bytes(b"fake checkpoint; never loaded")
            calls = []
            def runner(module, *args):
                calls.append((module, args))
                out = Path(args[args.index("--out") + 1])
                out.mkdir(exist_ok=True)
                plan = seating_plan(COLLECTION_SEEDS)
                report = {"plan": plan, "finished_at": "test", "games": [
                    {**item, "success": True, "terminal": True, "truncated": False} for item in plan]}
                (out / "evaluation.json").write_text(json.dumps(report))
            with patch("cedhai.next_experiment.require_cloud"), patch("cedhai.next_experiment.sha256", return_value=REFERENCE_HASH):
                result = experiment(root / "experiment", reference, "collect", runner=runner)
                self.assertTrue(result["collection_complete"])
                experiment(root / "experiment", reference, "collect", runner=runner)
                self.assertIn("--resume", calls[-1][1])
                config = root / "experiment/experiment.json"
                changed = json.loads(config.read_text())
                changed["epochs"] = 99
                config.write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, "code/configuration changed"):
                    experiment(root / "experiment", reference, "collect", runner=runner)

    def test_seed_groups_and_cloud_guard(self):
        self.assertFalse(set(COLLECTION_SEEDS) & set(EVALUATION_SEEDS))
        self.assertFalse(set(DEVELOPMENT_SEEDS) & set(EVALUATION_SEEDS))
        with patch("cedhai.next_experiment.os.name", "nt"):
            with self.assertRaisesRegex(ValueError, "hosted Colab"):
                experiment(None, None, "collect", runner=lambda *args: self.fail("No command should run locally"))

    def test_incomplete_collection_is_rejected_and_partial_paths_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, _ = documents()
            report["games"].pop()
            (root / "evaluation.json").write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "incomplete"):
                require_complete(root)
            existing = root / "model"
            existing.mkdir()
            self.assertEqual(fresh_path(root, "model").name, "model-attempt2")
            (root / "comparison.json").write_text("{}")
            self.assertEqual(fresh_path(root, "comparison", ".json").name, "comparison-attempt2.json")

    def test_comparison_pairs_rotations_by_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = root / "reference.zip", root / "candidate.zip"
            archive(a)
            archive(b, candidate=True)
            report = compare(a, b)
            self.assertEqual(report["independent_seed_blocks"], 5)
            self.assertEqual(report["reference_win_rate"], 0.25)
            self.assertEqual(report["candidate_win_rate"], 1.0)
            self.assertEqual(report["win_rate_difference"], 0.75)
            self.assertEqual(report["paired_seed_bootstrap_95"], [0.75, 0.75])

    def test_mismatched_experiment_or_same_checkpoint_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a, b = root / "reference.zip", root / "candidate.zip"
            archive(a)
            archive(b)
            with self.assertRaisesRegex(ValueError, "identical"):
                compare(a, b)
            evaluation, diagnostics = archive(b, candidate=True)
            evaluation["experiment"]["turns"] = 50
            with zipfile.ZipFile(b, "w") as writer:
                writer.writestr("evaluation.json", json.dumps(evaluation))
                writer.writestr("diagnostics.json", json.dumps(diagnostics))
            with self.assertRaisesRegex(ValueError, "settings differ"):
                compare(a, b)
