import json
from pathlib import Path
import tempfile
import unittest

from cedhai.dataset_report import audit_dataset
from cedhai.learning_data import ACTION_SIZE, MAX_ACTIONS, STATE_SIZE, examples
from tests.test_learning_data import episode, save_episode


def dataset(path):
    items, rows = [], []
    for seed in (7, 10):
        source = path / str(seed)
        source.mkdir()
        events = episode()
        for event in events:
            if "request_id" in event:
                event["request_id"] = event["request_id"].replace("xmage-7", f"xmage-{seed}")
            if "observation" in event:
                event["observation"]["game_id"] = f"xmage-{seed}"
                event["response"]["request_id"] = event["request_id"]
        events[-1]["game_id"] = f"xmage-{seed}"
        save_episode(source, events, seed)
        metadata, exported = examples(source)
        items.append({"episode_id": metadata["episode_id"], "seed": seed, "rows": len(exported)})
        rows.extend(exported)
    manifest = {"schema_version": 1, "state_size": STATE_SIZE, "action_size": ACTION_SIZE,
                "max_actions": MAX_ACTIONS, "episodes": items, "rows": len(rows)}
    (path / "manifest.json").write_text(json.dumps(manifest))
    return rows


class DatasetReportTests(unittest.TestCase):
    def test_valid_data_reports_coverage_and_small_sample_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            rows = dataset(path)
            (path / "examples.jsonl").write_text("\n".join(map(json.dumps, rows)))
            report = audit_dataset(path)
            self.assertTrue(report["smoke_training_ready"])
            self.assertEqual(report["splits"]["train"]["choices"], 3)
            self.assertTrue(any("no meaningful block" in warning for warning in report["warnings"]))

    def test_corruption_is_rejected(self):
        for problem in ("split", "mask", "transition", "padding", "terminal", "count"):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp)
                rows = dataset(path)
                if problem == "split":
                    rows[0]["split"] = "validation"
                elif problem == "mask":
                    rows[0]["selected_index"] = 31
                elif problem == "transition":
                    rows[0]["next_state"] = [9] * STATE_SIZE
                elif problem == "padding":
                    rows[0]["actions"][31][0] = 1
                elif problem == "terminal":
                    rows[2].update(terminated=False, reward=0, next_state=rows[2]["state"])
                else:
                    rows.pop()
                (path / "examples.jsonl").write_text("\n".join(map(json.dumps, rows)))
                with self.assertRaises(ValueError):
                    audit_dataset(path)
