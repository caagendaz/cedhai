import json
from pathlib import Path
import tempfile
import unittest
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
