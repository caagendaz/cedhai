from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from cedhai.evaluate import seating_plan, summarize
from cedhai.review_results import import_results, read_archive, validate


def documents():
    policies = ["model", "defend", "defend", "defend"]
    plan = seating_plan([14, 16, 17, 18, 19])
    checkpoint = {"sha256": "a" * 64, "training_dataset_sha256": "b" * 64, "epoch": 5}
    games = [{**item, "run": f"/content/drive/game{index}", "success": True,
              "terminal": True, "truncated": False, "winners": [0], "decisions": 8,
              "decision_counts_by_seat": [{"decisions": 2, "choices": 1,
                                           "scopes": {"attack": 1}, "selected": {"attack": 1}} for _ in range(4)]}
             for index, item in enumerate(plan)]
    evaluation = {"schema_version": 2, "policies": policies, "plan": plan, "checkpoint": checkpoint,
                  "development_seeds": [7, 10, 11, 12, 13, 20], "games": games,
                  "finished_at": "2026-10-13T00:00:00Z"}
    evaluation["experiment"] = {k: deepcopy(evaluation[k]) for k in ("plan", "policies", "checkpoint", "development_seeds")}
    evaluation["summary"] = summarize(games, policies)
    diagnostic = {"schema_version": 1, "accepted_games": 20, "rejected": [],
                  "profiles": [{"profile": i, "policy": p, "counts": {
                      "decisions": 40, "choices": 20, "forced": 20, "selected_attack": 20,
                      "attack_opportunities": 20, "attack_selected": 20, "attack_declined": 0}}
                               for i, p in enumerate(policies)]}
    return evaluation, diagnostic


class ReviewResultsTests(unittest.TestCase):
    def test_review_import_is_portable_and_preserves_original_json(self):
        evaluation, diagnostic = documents()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "summary.zip"
            raw = json.dumps(evaluation).encode()
            with zipfile.ZipFile(archive, "w") as writer:
                writer.writestr("evaluation.json", raw)
                writer.writestr("diagnostics.json", json.dumps(diagnostic))
            report = import_results(archive, root / "review")
            self.assertTrue(report["batch_complete"])
            self.assertEqual(report["summary"]["profiles"][0]["wins"], 5)
            self.assertEqual(report["summary"]["complete_seed_blocks"], 5)
            self.assertEqual((root / "review/evaluation.json").read_bytes(), raw)
            self.assertIn("25.0%", (root / "review/review.md").read_text())
            with self.assertRaises(FileExistsError):
                import_results(archive, root / "review")

    def test_corrupted_or_stale_results_are_rejected(self):
        for problem in ("summary", "duplicate", "seating", "seed", "flags", "winners", "counts", "diagnostics", "opportunities"):
            with self.subTest(problem=problem):
                evaluation, diagnostic = documents()
                if problem == "summary":
                    evaluation["summary"]["profiles"][0]["wins"] += 1
                elif problem == "duplicate":
                    evaluation["games"].append(deepcopy(evaluation["games"][0]))
                elif problem == "seating":
                    evaluation["games"][0]["seat_to_profile"] = [3, 2, 1, 0]
                elif problem == "seed":
                    evaluation["development_seeds"].append(14)
                elif problem == "flags":
                    evaluation["games"][0]["truncated"] = True
                elif problem == "winners":
                    evaluation["games"][0]["winners"] = [True]
                elif problem == "counts":
                    evaluation["games"][0]["decisions"] += 1
                elif problem == "diagnostics":
                    diagnostic["profiles"][0]["counts"]["decisions"] += 1
                else:
                    diagnostic["profiles"][0]["counts"]["attack_declined"] = 1
                with self.assertRaises(ValueError):
                    validate(evaluation, diagnostic)

    def test_missing_games_are_not_declared_complete(self):
        evaluation, diagnostic = documents()
        evaluation["games"] = evaluation["games"][:-4]
        evaluation["summary"] = summarize(evaluation["games"], evaluation["policies"])
        diagnostic["accepted_games"] = 16
        for profile in diagnostic["profiles"]:
            profile["counts"] = {key: value * 4 // 5 for key, value in profile["counts"].items()}
        report = validate(evaluation, diagnostic)
        self.assertFalse(report["batch_complete"])
        self.assertEqual(report["missing"], 4)

    def test_unexpected_archive_members_are_not_extracted(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as writer:
                writer.writestr("../escape.py", "raise Exception()")
                writer.writestr("evaluation.json", "{}")
            with self.assertRaises(ValueError):
                read_archive(archive)
            self.assertFalse((Path(tmp).parent / "escape.py").exists())
