"""Audit exported curriculum data before a policy/value training experiment."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path

from .learning_data import ACTION_SIZE, MAX_ACTIONS, SCOPES, STATE_SIZE


def vector(value, size):
    if not isinstance(value, list) or len(value) != size or any(
        type(x) not in (int, float) or not math.isfinite(x) for x in value
    ):
        raise ValueError("Invalid numeric feature vector")


def audit_dataset(path: Path) -> dict:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("schema_version"), manifest.get("state_size"),
        manifest.get("action_size"), manifest.get("max_actions")) != (1, STATE_SIZE, ACTION_SIZE, MAX_ACTIONS):
        raise ValueError("Incompatible dataset schema")
    episodes = {item["episode_id"]: item for item in manifest["episodes"]}
    if len(episodes) != len(manifest["episodes"]):
        raise ValueError("Duplicate manifest episode")
    counts = Counter()
    splits = defaultdict(lambda: {"rows": 0, "choices": 0, "scopes": Counter(),
                                   "policy_choices": Counter(), "seeds": set(), "episodes": set()})
    previous = {}
    with (path / "examples.jsonl").open(encoding="utf-8") as reader:
        for line in reader:
            row = json.loads(line)
            episode = episodes.get(row["episode_id"])
            if episode is None or row["seed"] != episode["seed"]:
                raise ValueError("Unknown episode or inconsistent seed")
            split = "validation" if row["seed"] % 5 == 0 else "train"
            if row["split"] != split or row["scope"] not in SCOPES or type(row["seat"]) is not int or row["seat"] not in range(4):
                raise ValueError("Invalid split, scope or actor")
            vector(row["state"], STATE_SIZE)
            if len(row["actions"]) != MAX_ACTIONS:
                raise ValueError("Incorrect action padding")
            for action in row["actions"]:
                vector(action, ACTION_SIZE)
            mask = row["action_mask"]
            count = row["choice_count"]
            if type(count) is not int or not 1 <= count <= MAX_ACTIONS or mask != [True] * count + [False] * (MAX_ACTIONS - count) or any(type(x) is not bool for x in mask):
                raise ValueError("Invalid legal-action mask")
            if type(row["selected_index"]) is not int or not 0 <= row["selected_index"] < count:
                raise ValueError("Selected action is masked out")
            if row["policy_weight"] != float(count > 1) or row["outcome_target"] not in (0.0, 1.0):
                raise ValueError("Invalid learning label")
            if any(any(action) for action in row["actions"][count:]):
                raise ValueError("Nonzero padded action")
            key = (row["episode_id"], row["seat"])
            prior = previous.get(key)
            if prior and (prior["terminated"] or prior["next_state"] != row["state"] or prior["step"] >= row["step"] or prior["outcome_target"] != row["outcome_target"]):
                raise ValueError("Broken actor transition chain")
            if type(row["terminated"]) is not bool or row["reward"] != (row["outcome_target"] if row["terminated"] else 0.0):
                raise ValueError("Invalid transition reward")
            if row["terminated"]:
                if row["next_state"] is not None:
                    raise ValueError("Terminal transition has a next state")
            else:
                vector(row["next_state"], STATE_SIZE)
            previous[key] = row
            counts[row["episode_id"]] += 1
            stats = splits[split]
            stats["rows"] += 1
            stats["choices"] += int(count > 1)
            stats["scopes"][row["scope"]] += int(count > 1)
            stats["policy_choices"][row["policy"]] += int(count > 1)
            stats["seeds"].add(row["seed"])
            stats["episodes"].add(row["episode_id"])
    if not counts or sum(counts.values()) != manifest["rows"] or any(counts[e] != item["rows"] for e, item in episodes.items()):
        raise ValueError("Manifest row counts disagree")
    if any(not row["terminated"] for row in previous.values()):
        raise ValueError("Missing actor terminal transition")
    warnings = []
    for split in ("train", "validation"):
        stats = splits[split]
        if not stats["choices"]:
            warnings.append(f"{split}: no meaningful policy choices")
        if len(stats["seeds"]) < 5:
            warnings.append(f"{split}: fewer than five independent seeds; metrics are exploratory")
        for scope in SCOPES:
            if not stats["scopes"][scope]:
                warnings.append(f"{split}: no meaningful {scope} choices")
        stats["seeds"] = sorted(stats["seeds"])
        stats["episodes"] = len(stats["episodes"])
    return {"schema_version": 1, "integrity_passed": True,
            "smoke_training_ready": all(splits[s]["choices"] for s in ("train", "validation")),
            "splits": dict(splits), "rejected_sources": manifest.get("rejected", []),
            "warnings": warnings,
            "label_note": "Scripted/random behavior labels, not optimal actions. Readiness means a training smoke test, not competitive evidence."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_dataset(args.dataset)
    except (ValueError, KeyError, OSError, TypeError) as ex:
        raise SystemExit(f"Dataset audit failed: {ex}") from ex
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["smoke_training_ready"] else 1)


if __name__ == "__main__":
    main()
