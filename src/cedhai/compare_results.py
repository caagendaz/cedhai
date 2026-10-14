"""Compare two complete, matched evaluation summaries using paired seed blocks."""

import argparse
import json
from pathlib import Path
import random

from .review_results import read_archive


def compare(reference: Path, candidate: Path):
    a_raw, a_review = read_archive(reference)
    b_raw, b_review = read_archive(candidate)
    if not a_review["batch_complete"] or not b_review["batch_complete"]:
        raise ValueError("Comparison needs two complete, nontruncated batches")
    a = json.loads(a_raw["evaluation.json"])
    b = json.loads(b_raw["evaluation.json"])
    if a["policies"] != b["policies"] or a["policies"].count("model") != 1:
        raise ValueError("Require the same profiles and exactly one model")
    for field in ("plan", "development_seeds", "turns", "timeout", "deck_sha256", "bridge_sha256"):
        if field not in a["experiment"] or a["experiment"][field] != b["experiment"].get(field):
            raise ValueError("Matched experiment settings differ: " + field)
    if a["checkpoint"]["sha256"] == b["checkpoint"]["sha256"]:
        raise ValueError("Reference and candidate checkpoints are identical")
    profile = a["policies"].index("model")
    def wins(report):
        return {(game["seed"], game["rotation"]): int(any(game["seat_to_profile"][seat] == profile for seat in game["winners"]))
                for game in report["games"]}
    a_wins, b_wins = wins(a), wins(b)
    if a_wins.keys() != b_wins.keys():
        raise ValueError("Matched games differ")
    seeds = sorted({seed for seed, _ in a_wins})
    blocks = [{"seed": seed, "reference_wins": sum(a_wins[seed, rotation] for rotation in range(4)),
               "candidate_wins": sum(b_wins[seed, rotation] for rotation in range(4))} for seed in seeds]
    differences = [(block["candidate_wins"] - block["reference_wins"]) / 4 for block in blocks]
    interval = None
    if len(blocks) >= 5:
        rng = random.Random(0)
        samples = sorted(sum(rng.choice(differences) for _ in blocks) / len(blocks) for _ in range(2000))
        interval = [samples[49], samples[1949]]
    count = len(a_wins)
    return {"schema_version": 1, "games_per_checkpoint": count, "independent_seed_blocks": len(blocks),
            "reference_checkpoint": a["checkpoint"], "candidate_checkpoint": b["checkpoint"],
            "reference_win_rate": sum(a_wins.values()) / count, "candidate_win_rate": sum(b_wins.values()) / count,
            "win_rate_difference": sum(differences) / len(differences), "paired_seed_bootstrap_95": interval,
            "blocks": blocks,
            "limits": ["Paired bootstrap ranges are exploratory with few seeds and do not prove population-level improvement.",
                       "More training data and a larger epoch budget both changed; this is not a data-only causal comparison.",
                       "Summary integrity is not independent verification of raw trajectories. This remains vanilla Commander imitation, not cEDH or self-play RL."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.reference, args.candidate)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as writer:
        writer.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
