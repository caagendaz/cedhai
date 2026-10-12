"""Run one local curriculum pod with a checkpoint against scripted controls."""

import argparse
import hashlib
import json
from pathlib import Path

import torch

from .model import ModelAgent
from .agents import BaselineAgent
from .run_bridge import ROOT, run_bridge


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--seat", type=int, choices=range(4), default=0)
    parser.add_argument("--turns", type=int, default=100)
    args = parser.parse_args()
    torch.set_num_threads(1)
    learned = ModelAgent(args.checkpoint)
    agents = tuple(learned if seat == args.seat else BaselineAgent(args.seed + seat, "defend")
                   for seat in range(4))
    deck = ROOT / "examples/decks/curriculum/yargle.txt"
    result = run_bridge(next((ROOT / "tools/jdk").glob("jdk-*")), ROOT / "tools/magezero/xmage",
                        [deck] * 4, args.out, args.seed, "random", args.turns, 300, "basic", agents=agents)
    provenance = {"checkpoint_sha256": hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
                  "training_dataset_sha256": learned.checkpoint["dataset_sha256"],
                  "epoch": learned.checkpoint["epoch"], "model_seat": args.seat,
                  "opponents": "defend scripted controls", "success": result["success"]}
    (args.out / "model.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    completion = result["completion"] or {}
    print(json.dumps({**provenance, "completion": {key: value for key, value in completion.items()
                                                   if key != "public_state"}}, indent=2))
    raise SystemExit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
