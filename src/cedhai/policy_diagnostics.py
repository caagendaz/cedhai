"""Describe available-choice behavior without labeling tactical choices optimal."""

import argparse
from collections import Counter
import json
from pathlib import Path


def analyze_run(path: Path):
    metadata = json.loads((path / "result.json").read_text(encoding="utf-8"))
    if not metadata.get("success") or metadata.get("mode") != "basic":
        raise ValueError("Diagnostics require a successful basic-mode run")
    seats = [Counter() for _ in range(4)]
    final = None
    with (path / "trajectory.jsonl").open(encoding="utf-8") as reader:
        for line in reader:
            event = json.loads(line)
            final = event
            if event["event"] != "decision":
                continue
            data = event["observation"]
            ids = [action["id"] for action in data["legal_actions"]]
            selected = event["response"]["action_id"]
            if selected not in ids or len(ids) != len(set(ids)):
                raise ValueError("Invalid recorded legal choice")
            counts = seats[data["seat"]]
            counts["decisions"] += 1
            if len(ids) == 1:
                counts["forced"] += 1
                continue
            counts["choices"] += 1
            kind = selected.split(":", 1)[0]
            counts["selected_" + kind] += 1
            available = {action.split(":", 1)[0] for action in ids}
            for option in ("land", "cast", "attack", "block"):
                if option in available:
                    counts[option + "_opportunities"] += 1
                    counts[option + "_selected"] += int(kind == option)
                    counts[option + "_declined"] += int(kind != option)
            if event["scope"] == "priority_basic" and "cast" in available and "land" not in available:
                counts["cast_without_land_opportunities"] += 1
                counts["cast_without_land_passes"] += int(kind == "pass")
    if final != metadata.get("completion") or not final or final.get("event") != "finished":
        raise ValueError("Missing or inconsistent completion")
    return seats


def diagnose_evaluation(path: Path):
    evaluation = json.loads(path.read_text(encoding="utf-8"))
    profiles = [Counter() for _ in range(4)]
    accepted, rejected = 0, []
    for game in evaluation["games"]:
        if not game["success"]:
            rejected.append({"run": game["run"], "reason": "Failed game"})
            continue
        try:
            seats = analyze_run(Path(game["run"]))
            if sorted(game["seat_to_profile"]) != list(range(4)):
                raise ValueError("Invalid profile mapping")
            for seat, counts in enumerate(seats):
                profiles[game["seat_to_profile"][seat]].update(counts)
            accepted += 1
        except (ValueError, KeyError, OSError) as ex:
            rejected.append({"run": game["run"], "reason": str(ex)})
    return {"schema_version": 1, "accepted_games": accepted, "rejected": rejected,
            "profiles": [{"profile": index, "policy": evaluation["policies"][index],
                          "counts": dict(counts)} for index, counts in enumerate(profiles)],
            "interpretation": "Available-choice behavior only. Passing or skipping may be tactically correct; these are not optimal-action labels."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("Choose a new output file")
    report = diagnose_evaluation(args.evaluation)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as writer:
        writer.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    raise SystemExit(1 if report["rejected"] or not report["accepted_games"] else 0)


if __name__ == "__main__":
    main()
