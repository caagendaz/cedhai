"""Seeded behavior-cloning/value smoke trainer for audited Commander curricula."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import random

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
import torch
from torch.nn import functional as F

from .dataset_report import audit_dataset
from .learning_data import ACTION_SIZE, MAX_ACTIONS, STATE_SIZE
from .model import PolicyValueModel, load_checkpoint


def fingerprint(path):
    digest = hashlib.sha256()
    for name in ("manifest.json", "examples.jsonl"):
        with (path / name).open("rb") as reader:
            for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def tensors(rows, device):
    return (torch.tensor([r["state"] for r in rows], dtype=torch.float32, device=device),
            torch.tensor([r["actions"] for r in rows], dtype=torch.float32, device=device),
            torch.tensor([r["action_mask"] for r in rows], dtype=torch.bool, device=device),
            torch.tensor([r["selected_index"] for r in rows], device=device),
            torch.tensor([r["outcome_target"] for r in rows], dtype=torch.float32, device=device))


def metrics(model, rows, device, batch_size):
    model.eval()
    totals = dict(policy_loss=0.0, value_loss=0.0, imitation_accuracy=0.0)
    with torch.inference_mode():
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            state, actions, mask, selected, outcome = tensors(batch, device)
            logits, value = model(state, actions, mask)
            totals["policy_loss"] += F.cross_entropy(logits, selected, reduction="sum").item()
            totals["value_loss"] += F.binary_cross_entropy_with_logits(value, outcome, reduction="sum").item()
            totals["imitation_accuracy"] += (logits.argmax(1) == selected).sum().item()
    return {**{key: value / len(rows) for key, value in totals.items()}, "examples": len(rows)}


def train(dataset: Path, out: Path, *, epochs=5, batch_size=64, hidden_size=64,
          learning_rate=0.001, seed=0, policies=("develop", "defend"), device="cpu", resume=None):
    if epochs < 1 or batch_size < 1 or hidden_size < 1 or learning_rate <= 0:
        raise ValueError("Training parameters must be positive")
    audit = audit_dataset(dataset)
    if not audit["smoke_training_ready"]:
        raise ValueError("Dataset is not ready for training")
    rows = {"train": [], "validation": []}
    with (dataset / "examples.jsonl").open(encoding="utf-8") as reader:
        for line in reader:
            row = json.loads(line)
            if row["policy"] in policies and row["policy_weight"] > 0:
                rows[row["split"]].append(row)
    if not all(rows.values()):
        raise ValueError("Both splits need meaningful choices from selected policies")
    config = dict(hidden_size=hidden_size, batch_size=batch_size, learning_rate=learning_rate,
                  seed=seed, policies=list(policies))
    source_hash = fingerprint(dataset)
    code_hashes = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                   for name in ("train.py", "model.py", "learning_data.py", "dataset_report.py")}
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    device = "cuda" if device == "auto" and torch.cuda.is_available() else "cpu" if device == "auto" else device
    model = PolicyValueModel(hidden_size)
    saved = None
    if resume:
        model, saved = load_checkpoint(Path(resume))
        if saved["config"] != config or saved["dataset_sha256"] != source_hash or saved["source_sha256"] != code_hashes:
            raise ValueError("Resume configuration or dataset differs")
    model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    start = saved["epoch"] if saved else 0
    if start >= epochs:
        raise ValueError("--epochs must exceed the resumed epoch")
    if saved:
        optimizer.load_state_dict(saved["optimizer"])
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema_version=1, config=config, dataset_sha256=source_hash, device=device,
                  source_sha256=code_hashes,
                  torch_version=str(torch.__version__), warnings=audit["warnings"], history=[],
                  method="Scripted behavior cloning plus outcome prediction, not self-play RL",
                  baseline={split: metrics(model, data, device, batch_size) for split, data in rows.items()})
    for epoch in range(start, epochs):
        order = list(rows["train"])
        random.Random(seed + epoch).shuffle(order)
        model.train()
        for offset in range(0, len(order), batch_size):
            state, actions, mask, selected, outcome = tensors(order[offset:offset + batch_size], device)
            logits, value = model(state, actions, mask)
            loss = F.cross_entropy(logits, selected) + 0.5 * F.binary_cross_entropy_with_logits(value, outcome)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
        item = {"epoch": epoch + 1, **{split: metrics(model, data, device, batch_size) for split, data in rows.items()}}
        report["history"].append(item)
        checkpoint = dict(schema_version=1, features=[STATE_SIZE, ACTION_SIZE, MAX_ACTIONS],
                          config=config, dataset_sha256=source_hash, epoch=epoch + 1,
                          source_sha256=code_hashes,
                          model=model.state_dict(), optimizer=optimizer.state_dict(),
                          torch_version=str(torch.__version__))
        temporary = out / "checkpoint.tmp"
        torch.save(checkpoint, temporary)
        temporary.replace(out / "latest.pt")
        (out / "metrics.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(item), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--hidden-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--policies", nargs="+", default=["develop", "defend"])
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args()
    train(args.dataset, args.out, epochs=args.epochs, batch_size=args.batch_size,
          hidden_size=args.hidden_size, learning_rate=args.learning_rate, seed=args.seed,
          policies=tuple(args.policies), device=args.device, resume=args.resume)


if __name__ == "__main__":
    main()
