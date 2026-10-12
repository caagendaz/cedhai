import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from tests.test_dataset_report import dataset


@unittest.skipUnless(importlib.util.find_spec("torch"), "optional PyTorch dependency")
class ModelTests(unittest.TestCase):
    def test_masking_checkpoint_and_external_agent(self):
        import torch
        from cedhai.engine import Action, Observation
        from cedhai.model import ModelAgent, PolicyValueModel, load_checkpoint
        from cedhai.train import train
        from tests.test_learning_data import observation
        model = PolicyValueModel()
        with self.assertRaises(ValueError):
            model(torch.zeros(1, 104), torch.zeros(1, 32, 21), torch.zeros(1, 32, dtype=torch.bool))
        mask = torch.zeros(1, 32, dtype=torch.bool)
        mask[0, 1] = True
        logits, _ = model(torch.zeros(1, 104), torch.zeros(1, 32, 21), mask)
        self.assertEqual(logits.argmax(1).item(), 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            rows = dataset(path)
            (path / "examples.jsonl").write_text("\n".join(map(json.dumps, rows)))
            out = path / "trained"
            train(path, out, epochs=1, policies=("random",))
            loaded, saved = load_checkpoint(out / "latest.pt")
            self.assertEqual(saved["epoch"], 1)
            agent = ModelAgent(out / "latest.pt")
            obs = observation()
            obs["legal_actions"] = tuple(Action(**item) for item in obs["legal_actions"])
            chosen = agent.choose_action(Observation(**obs, decision_type="priority_basic"))
            self.assertIn(chosen, obs["legal_actions"])
            resumed = path / "resumed"
            train(path, resumed, epochs=2, policies=("random",), resume=out / "latest.pt")
            direct = path / "direct"
            train(path, direct, epochs=2, policies=("random",))
            _, a = load_checkpoint(resumed / "latest.pt")
            _, b = load_checkpoint(direct / "latest.pt")
            self.assertTrue(all(torch.equal(a["model"][key], b["model"][key]) for key in a["model"]))
            with self.assertRaisesRegex(ValueError, "differs"):
                train(path, path / "bad", epochs=3, policies=("random",), seed=99, resume=out / "latest.pt")

    def test_notebook_code_is_valid_python(self):
        path = Path(__file__).resolve().parents[1] / "notebooks/colab_training.ipynb"
        notebook = json.loads(path.read_text())
        self.assertEqual(notebook["nbformat"], 4)
        for cell in notebook["cells"]:
            if cell["cell_type"] == "code":
                compile("".join(cell["source"]), str(path), "exec")
