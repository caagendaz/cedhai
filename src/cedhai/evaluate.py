"""Run matched seed blocks with every baseline rotated through each seat."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random

from .run_bridge import ROOT, run_bridge


def seating_plan(seeds: list[int]) -> list[dict]:
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("Require unique seed blocks")
    return [{"seed": seed, "rotation": rotation,
             "seat_to_profile": [(seat + rotation) % 4 for seat in range(4)]}
            for seed in seeds for rotation in range(4)]


def summarize(games: list[dict], policy_names: list[str]) -> dict:
    totals = [{"profile": index, "policy": policy, "wins": 0, "completed": 0,
               "draws": 0, "truncated": 0, "errors": 0} for index, policy in enumerate(policy_names)]
    blocks: dict[int, list[list[int]]] = {}
    for game in games:
        if not game["success"]:
            for row in totals:
                row["errors"] += 1
            continue
        if game["truncated"]:
            for row in totals:
                row["truncated"] += 1
            continue
        block = blocks.setdefault(game["seed"], [[0, 0] for _ in range(4)])
        winners = {game["seat_to_profile"][seat] for seat in game["winners"]}
        for index, row in enumerate(totals):
            row["completed"] += 1
            row["wins"] += int(index in winners)
            row["draws"] += int(not winners)
            block[index][0] += int(index in winners)
            block[index][1] += 1
    complete_blocks = [block for block in blocks.values() if all(pair[1] == 4 for pair in block)]
    for index, row in enumerate(totals):
        row["win_rate"] = row["wins"] / row["completed"] if row["completed"] else None
        row["seed_block_bootstrap_95"] = None
        if len(complete_blocks) >= 5:
            rng = random.Random(0)
            rates = sorted(sum(rng.choice(complete_blocks)[index][0] for _ in complete_blocks)
                           / (4 * len(complete_blocks)) for _ in range(2000))
            row["seed_block_bootstrap_95"] = [rates[49], rates[1949]]
    return {"profiles": totals, "complete_seed_blocks": len(complete_blocks),
            "uncertainty_note": "Intervals require at least five complete seed blocks; rotations sharing a seed are clustered."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deck", type=Path, default=ROOT / "examples/decks/curriculum/yargle.txt")
    parser.add_argument("--seeds", nargs="+", type=int, default=[7, 10])
    parser.add_argument("--policies", nargs=4, choices=("random", "land", "pass", "develop", "defend"),
                        default=["develop", "random", "random", "defend"])
    parser.add_argument("--turns", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    plan = seating_plan(args.seeds)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    jdk = next((ROOT / "tools/jdk").glob("jdk-*"))
    report = {"schema_version": 1, "started_at": datetime.now(timezone.utc).isoformat(),
              "policies": args.policies, "plan": plan, "games": []}
    def save():
        report["summary"] = summarize(report["games"], args.policies)
        (out / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    save()
    for item in plan:
        run_dir = out / f"seed{item['seed']}-rotation{item['rotation']}"
        policies = tuple(args.policies[index] for index in item["seat_to_profile"])
        result = run_bridge(jdk, ROOT / "tools/magezero/xmage", [args.deck] * 4, run_dir,
                            item["seed"], "random", args.turns, args.timeout, "basic", policies)
        completion = result["completion"] or {}
        game = {**item, "run": str(run_dir), "success": result["success"],
                "terminal": completion.get("terminal", False), "truncated": completion.get("truncated", False),
                "winners": completion.get("winners", []), "decisions": result["decisions"]}
        if game["success"] and not game["terminal"] and not game["truncated"]:
            game["success"] = False
        report["games"].append(game)
        save()
        print(json.dumps(game), flush=True)
        if not game["success"]:
            raise SystemExit("Evaluation stopped after failed game; inspect its logs")
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    save()
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
