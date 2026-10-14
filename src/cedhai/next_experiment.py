"""Resumable cloud-only data expansion, training, and paired model evaluation."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import zipfile

from .dataset_report import audit_dataset
from .review_results import read_archive

COLLECTION_SEEDS = [21, 22, 23, 24, 25, 26]
EVALUATION_SEEDS = [31, 32, 33, 34, 36]
DEVELOPMENT_SEEDS = [7, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20, *COLLECTION_SEEDS]
REFERENCE_HASH = "9ca52114aa913a470647456cea97a9dbabd7d1a4a3e582f75c3eaf52a21c9aef"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as reader:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_module(module, *args):
    print("Starting:", module, *map(str, args), flush=True)
    command = [sys.executable, "-u", "-m", "cedhai." + module, *map(str, args)]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                          start_new_session=True) as process:
        try:
            for line in process.stdout:
                print(line, end="", flush=True)
            if process.wait():
                raise subprocess.CalledProcessError(process.returncode, command)
        except BaseException:
            stop_process_group(process)
            raise


def stop_process_group(process):
    # Each module owns its process group, including any Java child processes.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def fresh_path(root, label, suffix=""):
    attempt = 1
    path = root / (label + suffix)
    while path.exists():
        attempt += 1
        path = root / f"{label}-attempt{attempt}{suffix}"
    return path


def require_complete(path):
    report = json.loads((path / "evaluation.json").read_text())
    if len(report["games"]) != len(report["plan"]) or not report.get("finished_at") or any(
        not game["success"] or not game["terminal"] or game["truncated"] for game in report["games"]
    ):
        raise ValueError("Batch is incomplete/failed/truncated; inspect logs before continuing")
    return report


def require_cloud():
    if os.name != "posix" or not Path("/content").is_dir():
        raise ValueError("This workflow must run on hosted Colab/Linux, not the local PC")


def experiment(root: Path, reference: Path, stage: str, runner=run_module):
    require_cloud()
    if set(COLLECTION_SEEDS) & set(EVALUATION_SEEDS) or set(DEVELOPMENT_SEEDS) & set(EVALUATION_SEEDS):
        raise ValueError("Seed groups overlap")
    if sha256(reference) != REFERENCE_HASH:
        raise ValueError("Reference is not the reviewed epoch-5 checkpoint")
    root.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).parent
    config = {"collection_seeds": COLLECTION_SEEDS, "evaluation_seeds": EVALUATION_SEEDS,
              "development_seeds": DEVELOPMENT_SEEDS, "epochs": 20, "training_seed": 0,
              "reference_sha256": REFERENCE_HASH,
              "source_sha256": {path.name: sha256(path) for path in sorted(source.glob("*.py"))}}
    config_path = root / "experiment.json"
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        raise ValueError("Experiment code/configuration changed; use the original bundle or a new run name")
    if not config_path.exists():
        save(config_path, config)
    frozen_reference = root / "reference.pt"
    if not frozen_reference.exists():
        shutil.copyfile(reference, frozen_reference)
    if sha256(frozen_reference) != REFERENCE_HASH:
        raise ValueError("Frozen reference checkpoint changed")
    state_path = root / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    collection = root / "collection"
    if stage == "collect":
        args = ["--seeds", *COLLECTION_SEEDS, "--out", collection]
        if (collection / "evaluation.json").exists():
            args.append("--resume")
        runner("evaluate", *args)
        require_complete(collection)
        state["collection_complete"] = True
    elif stage == "train":
        report = require_complete(collection)
        if "dataset" not in state:
            dataset = fresh_path(root, "dataset")
            runner("learning_data", "--runs", *[game["run"] for game in report["games"]], "--out", dataset)
            audit = audit_dataset(dataset)
            if not audit["smoke_training_ready"] or audit["rejected_sources"]:
                raise ValueError("Dataset audit failed or rejected sources; do not train")
            state["dataset"] = str(dataset)
            save(state_path, state)
        dataset = Path(state["dataset"])
        audit = audit_dataset(dataset)
        if not audit["smoke_training_ready"] or audit["rejected_sources"]:
            raise ValueError("Saved dataset is not training-ready")
        print(json.dumps(audit, indent=2), flush=True)
        prior = Path(state["training_run"]) if "training_run" in state else None
        checkpoint = prior / "latest.pt" if prior else None
        if (checkpoint is None or not checkpoint.exists()) and state.get("resume_checkpoint"):
            checkpoint = Path(state["resume_checkpoint"])
        if checkpoint and checkpoint.exists():
            from .model import load_checkpoint
            _, saved = load_checkpoint(checkpoint)
            if saved["epoch"] == 20:
                state["candidate"] = str(checkpoint)
                save(state_path, state)
                print("Training already complete:", checkpoint, flush=True)
                return state
        output = fresh_path(root, "model")
        args = ["--dataset", dataset, "--out", output, "--epochs", 20, "--device", "cpu"]
        if checkpoint and checkpoint.exists():
            args += ["--resume", checkpoint]
            state["resume_checkpoint"] = str(checkpoint)
        state["training_run"] = str(output)
        save(state_path, state)
        runner("train", *args)
        state["candidate"] = str(output / "latest.pt")
    elif stage == "evaluate":
        if "candidate" not in state:
            raise ValueError("Complete the training stage first")
        for label, checkpoint in (("reference", frozen_reference), ("candidate", Path(state["candidate"]))):
            output = root / (label + "-evaluation")
            args = ["--checkpoint", checkpoint, "--policies", "model", "defend", "defend", "defend",
                    "--seeds", *EVALUATION_SEEDS, "--development-seeds", *DEVELOPMENT_SEEDS, "--out", output]
            if (output / "evaluation.json").exists():
                args.append("--resume")
            runner("evaluate", *args)
            require_complete(output)
        state["evaluation_complete"] = True
    elif stage == "export":
        archives = []
        for label in ("reference", "candidate"):
            output = root / (label + "-evaluation")
            require_complete(output)
            diagnostics = fresh_path(root, label + "-diagnostics", ".json")
            # Diagnostics may change after resumed evaluation; regenerate them each export.
            runner("policy_diagnostics", "--evaluation", output / "evaluation.json", "--out", diagnostics)
            archive = root / (label + "-summary.zip")
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as writer:
                writer.write(output / "evaluation.json", "evaluation.json")
                writer.write(diagnostics, "diagnostics.json")
            read_archive(archive)
            shutil.copyfile(archive, Path("/content") / archive.name)
            archives.append(archive)
        comparison = fresh_path(root, "comparison", ".json")
        runner("compare_results", "--reference", archives[0], "--candidate", archives[1], "--out", comparison)
        shutil.copyfile(comparison, Path("/content/comparison.json"))
        print("Download /content/reference-summary.zip, candidate-summary.zip, and comparison.json", flush=True)
        state["comparison"] = str(comparison)
    else:
        raise ValueError("Unknown experiment stage")
    save(state_path, state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--stage", choices=("collect", "train", "evaluate", "export"), required=True)
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise KeyboardInterrupt("Experiment interrupted; completed stages remain saved")
    signal.signal(signal.SIGTERM, interrupted)
    experiment(args.root, args.reference, args.stage)


if __name__ == "__main__":
    main()
