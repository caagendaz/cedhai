import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from cedhai.colab_bundle import bundle
from tests.test_dataset_report import dataset


class ColabBundleTests(unittest.TestCase):
    def test_archive_contains_only_source_and_audited_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            rows = dataset(path)
            (path / "examples.jsonl").write_text("\n".join(map(json.dumps, rows)))
            target = path / "colab.zip"
            bundle(path, target)
            with zipfile.ZipFile(target) as archive:
                names = archive.namelist()
                metadata = json.loads(archive.read("bundle.json"))
                self.assertIn("project/src/cedhai/train.py", names)
                self.assertIn("project/java/cedhai/BridgeMain.java", names)
                self.assertIn("project/examples/decks/curriculum/yargle.txt", names)
                self.assertIn("dataset/examples.jsonl", names)
                self.assertEqual(set(names), set(metadata["sha256"]) | {"bundle.json"})
                self.assertFalse(any(".git/" in name or ".venv/" in name or "tools/" in name for name in names))
            notebook = json.loads((Path(__file__).resolve().parents[1] / "notebooks/colab_training.ipynb").read_text())
            extract_code = "".join(notebook["cells"][2]["source"])
            extract_code = extract_code.replace("/content/cedhai-training", str(path / "extracted").replace("\\", "/"))
            exec(compile(extract_code, "colab extraction", "exec"), {"archive_path": str(target)})
            self.assertEqual((path / "extracted/dataset/examples.jsonl").read_bytes(), (path / "examples.jsonl").read_bytes())
            with self.assertRaises(FileExistsError):
                bundle(path, target)

    def test_cloud_notebook_cells_compile(self):
        path = Path(__file__).resolve().parents[1] / "notebooks/colab_simulation.ipynb"
        for cell in json.loads(path.read_text())["cells"]:
            if cell["cell_type"] == "code":
                compile("".join(cell["source"]), str(path), "exec")

    def test_vscode_notebook_avoids_browser_transfer_widgets(self):
        path = Path(__file__).resolve().parents[1] / "notebooks/colab_vscode.ipynb"
        code = ""
        for cell in json.loads(path.read_text())["cells"]:
            if cell["cell_type"] == "code":
                source = "".join(cell["source"])
                compile(source, str(path), "exec")
                code += source
        self.assertNotIn("files.upload(", code)
        self.assertNotIn("files.download(", code)
        self.assertIn("Select a remote Colab kernel", code)
        with patch("platform.system", return_value="Windows"), self.assertRaisesRegex(RuntimeError, "remote Colab kernel"):
            notebook = json.loads(path.read_text())
            exec("".join(notebook["cells"][1]["source"]), {})

    def test_summary_export_exposes_zip_at_remote_root(self):
        path = Path(__file__).resolve().parents[1] / "notebooks/colab_vscode.ipynb"
        notebook = json.loads(path.read_text())
        source = next("".join(cell["source"]) for cell in notebook["cells"]
                      if cell["cell_type"] == "code" and "summary_zip =" in "".join(cell["source"]))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evaluation = root / "evaluation"
            evaluation.mkdir()
            (evaluation / "evaluation.json").write_text("{}")
            diagnostics = root / "diagnostics.json"
            diagnostics.write_text("{}")
            target = root / "remote-root-summary.zip"
            source = source.replace("/content/evaluation-summary.zip", target.as_posix())
            exec(source, {"Path": Path, "run_root": root, "evaluation": evaluation,
                          "diagnostics_path": diagnostics})
            self.assertTrue(target.exists())
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(set(archive.namelist()), {"evaluation.json", "diagnostics.json"})
