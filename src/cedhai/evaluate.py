"""Run matched seed blocks with every baseline rotated through each seat."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import shutil

from .agents import BaselineAgent

from .run_bridge import ROOT, run_bridge


def seating_plan(seeds: list[int]) -> list[dict]:
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("Require unique seed blocks")
    return [{"seed": seed, "rotation": rotation,
             "seat_to_profile": [(seat + rotation) % 4 for seat in range(4)]}
            for seed in seeds for rotation in range(4)]


def summarize(games: list[dict], policy_names: list[str]) -> dict:
    totals = [{"profile": index, "policy": policy, "wins": 0, "completed": 0,
               "draws": 0, "truncated": 0, "errors": 0,
               "seats": [{"seat": seat, "wins": 0, "completed": 0, "truncated": 0, "errors": 0}
                         for seat in range(4)]} for index, policy in enumerate(policy_names)]
    if len(policy_names) != 4:
        raise ValueError("Require four policy profiles")
    blocks: dict[int, list[list[int]]] = {}
    seen = set()
    for game in games:
        mapping = game["seat_to_profile"]
        if sorted(mapping) != list(range(4)):
            raise ValueError("Invalid seating permutation")
        key = (game["seed"], tuple(mapping))
        if key in seen:
            raise ValueError("Duplicate seeded seating result")
        seen.add(key)
        if not game["success"] or (not game["terminal"] and not game["truncated"]):
            for profile, row in enumerate(totals):
                row["errors"] += 1
                row["seats"][mapping.index(profile)]["errors"] += 1
            continue
        if game["truncated"]:
            for profile, row in enumerate(totals):
                row["truncated"] += 1
                row["seats"][mapping.index(profile)]["truncated"] += 1
            continue
        if len(set(game["winners"])) != len(game["winners"]) or any(type(seat) is not int or seat not in range(4) for seat in game["winners"]):
            raise ValueError("Invalid winner seats")
        block = blocks.setdefault(game["seed"], [[0, 0] for _ in range(4)])
        winners = {game["seat_to_profile"][seat] for seat in game["winners"]}
        for index, row in enumerate(totals):
            row["completed"] += 1
            row["wins"] += int(index in winners)
            row["draws"] += int(not winners)
            seat = row["seats"][mapping.index(index)]
            seat["completed"] += 1
            seat["wins"] += int(index in winners)
            block[index][0] += int(index in winners)
            block[index][1] += 1
    complete_blocks = [block for block in blocks.values() if all(pair[1] == 4 for pair in block)]
    for index, row in enumerate(totals):
        row["win_rate"] = row["wins"] / row["completed"] if row["completed"] else None
        for seat in row["seats"]:
            seat["win_rate"] = seat["wins"] / seat["completed"] if seat["completed"] else None
        row["seed_block_bootstrap_95"] = None
        if len(complete_blocks) >= 5:
            rng = random.Random(0)
            rates = sorted(sum(rng.choice(complete_blocks)[index][0] for _ in complete_blocks)
                           / (4 * len(complete_blocks)) for _ in range(2000))
            row["seed_block_bootstrap_95"] = [rates[49], rates[1949]]
    return {"profiles": totals, "complete_seed_blocks": len(complete_blocks),
            "interval_caveat": "Bootstrap ranges describe observed seed blocks; zero-width ranges do not prove a true rate of zero or one.",
            "uncertainty_note": "Intervals require at least five complete seed blocks; rotations sharing a seed are clustered."}


def validate_experiment(seeds, development_seeds, policies, checkpoint):
    seating_plan(seeds)
    if set(seeds) & set(development_seeds):
        raise ValueError("Evaluation seeds overlap declared development seeds")
    if ("model" in policies) != (checkpoint is not None):
        raise ValueError("Specify both a model policy profile and --checkpoint")


def decision_counts(path):
    counts = [{"decisions": 0, "choices": 0, "scopes": {}, "selected": {}} for _ in range(4)]
    with (path / "trajectory.jsonl").open(encoding="utf-8") as reader:
        for line in reader:
            event = json.loads(line)
            if event["event"] != "decision":
                continue
            row = counts[event["observation"]["seat"]]
            row["decisions"] += 1
            if len(event["observation"]["legal_actions"]) > 1:
                row["choices"] += 1
                scope = event["scope"]
                row["scopes"][scope] = row["scopes"].get(scope, 0) + 1
                kind = event["response"]["action_id"].split(":", 1)[0]
                row["selected"][kind] = row["selected"].get(kind, 0) + 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deck", type=Path, default=ROOT / "examples/decks/curriculum/yargle.txt")
    parser.add_argument("--seeds", nargs="+", type=int, default=[7, 10])
    parser.add_argument("--policies", nargs=4, choices=("random", "land", "pass", "develop", "defend", "model"),
                        default=["develop", "random", "random", "defend"])
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--development-seeds", nargs="*", type=int, default=[])
    parser.add_argument("--turns", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--resume", action="store_true", help="Continue an identical saved experiment")
    args = parser.parse_args()
    validate_experiment(args.seeds, args.development_seeds, args.policies, args.checkpoint)
    learned = None
    checkpoint_info = None
    if args.checkpoint:
        import torch
        from .model import ModelAgent
        torch.set_num_threads(1)
        learned = ModelAgent(args.checkpoint)
        checkpoint_info = {"sha256": hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
                           "training_dataset_sha256": learned.checkpoint["dataset_sha256"],
                           "epoch": learned.checkpoint["epoch"]}
    plan = seating_plan(args.seeds)
    out = args.out.resolve()
    experiment = {"plan": plan, "policies": args.policies, "checkpoint": checkpoint_info,
                  "development_seeds": args.development_seeds, "turns": args.turns, "timeout": args.timeout,
                  "deck_sha256": hashlib.sha256(args.deck.read_bytes()).hexdigest(),
                  "bridge_sha256": hashlib.sha256((ROOT / "java/cedhai/BridgeMain.java").read_bytes()).hexdigest()}
    if args.resume:
        report = json.loads((out / "evaluation.json").read_text(encoding="utf-8"))
        if report.get("experiment") != experiment:
            raise ValueError("Resume experiment differs from saved configuration")
        failed = [game for game in report["games"] if not game["success"]]
        report.setdefault("failed_attempts", []).extend(failed)
        report["games"] = [game for game in report["games"] if game["success"]]
    else:
        out.mkdir(parents=True, exist_ok=False)
        report = {"schema_version": 2, "started_at": datetime.now(timezone.utc).isoformat(),
                  "policies": args.policies, "plan": plan, "games": [], "checkpoint": checkpoint_info,
                  "development_seeds": args.development_seeds, "experiment": experiment,
                  "seed_note": "Freshness is checked against declared seeds, not inferred from checkpoint weights.",
                  "policy_seed_rule": "engine seed + physical seat; reset each game"}
    jdk = next((ROOT / "tools/jdk").glob("jdk-*"))
    if args.checkpoint:
        if not args.resume:
            shutil.copyfile(args.checkpoint, out / "checkpoint.pt")
        learned = ModelAgent(out / "checkpoint.pt")
        if hashlib.sha256((out / "checkpoint.pt").read_bytes()).hexdigest() != checkpoint_info["sha256"]:
            raise ValueError("Checkpoint changed while creating evaluation snapshot")
    def save():
        report["summary"] = summarize(report["games"], args.policies)
        temporary = out / "evaluation.tmp"
        temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        temporary.replace(out / "evaluation.json")
    save()
    for item in plan:
        if any(game["seed"] == item["seed"] and game["rotation"] == item["rotation"] for game in report["games"]):
            continue
        run_dir = out / f"seed{item['seed']}-rotation{item['rotation']}"
        attempt = 1
        while run_dir.exists():
            attempt += 1
            run_dir = out / f"seed{item['seed']}-rotation{item['rotation']}-attempt{attempt}"
        policies = tuple(args.policies[index] for index in item["seat_to_profile"])
        agents = tuple(learned if policy == "model" else BaselineAgent(item["seed"] + seat, policy)
                       for seat, policy in enumerate(policies)) if learned else None
        bridge_policies = tuple("random" if policy == "model" else policy for policy in policies)
        try:
            result = run_bridge(jdk, ROOT / "tools/magezero/xmage", [args.deck] * 4, run_dir,
                                item["seed"], "random", args.turns, args.timeout, "basic", bridge_policies, agents)
        except Exception as ex:
            report["games"].append({**item, "run": str(run_dir), "success": False,
                                    "terminal": False, "truncated": False, "winners": [],
                                    "error": f"{type(ex).__name__}: {ex}"})
            save()
            raise
        completion = result["completion"] or {}
        game = {**item, "run": str(run_dir), "success": result["success"],
                "terminal": completion.get("terminal", False), "truncated": completion.get("truncated", False),
                "winners": completion.get("winners", []), "decisions": result["decisions"]}
        game["decision_counts_by_seat"] = decision_counts(run_dir)
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
