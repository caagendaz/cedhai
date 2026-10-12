"""Package audited data and Python source for Colab without GitHub credentials."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

from .dataset_report import audit_dataset

ROOT = Path(__file__).resolve().parents[2]


def bundle(dataset: Path, out: Path):
    report = audit_dataset(dataset)
    if not report["smoke_training_ready"]:
        raise ValueError("Dataset lacks training/validation choices")
    out.parent.mkdir(parents=True, exist_ok=True)
    revision = subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
                              cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    files = [(ROOT / "pyproject.toml", "project/pyproject.toml")]
    files += [(path, "project/" + path.relative_to(ROOT).as_posix()) for path in sorted((ROOT / "src/cedhai").glob("*.py"))]
    files += [(path, "project/" + path.relative_to(ROOT).as_posix()) for path in sorted((ROOT / "java/cedhai").glob("*.java"))]
    files += [(path, "project/" + path.relative_to(ROOT).as_posix()) for path in sorted((ROOT / "examples/decks/curriculum").glob("*.txt"))]
    files += [(dataset / name, "dataset/" + name) for name in ("manifest.json", "examples.jsonl")]
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for path, name in files}
    with zipfile.ZipFile(out, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, name in files:
            archive.write(path, name)
        archive.writestr("bundle.json", json.dumps({"schema_version": 1, "git_revision": revision,
                                                    "sha256": hashes, "audit": report}, indent=2))
    return {"archive": str(out.resolve()), "bytes": out.stat().st_size, "git_revision": revision}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(bundle(args.dataset, args.out), indent=2))


if __name__ == "__main__":
    main()
