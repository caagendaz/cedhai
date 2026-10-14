"""Review a downloaded Colab summary without executing or reopening cloud paths."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import zipfile

from .evaluate import seating_plan, summarize

MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024


def integer(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid {label}")
    return value


def validate(evaluation: dict, diagnostics: dict) -> dict:
    if not isinstance(evaluation, dict) or not isinstance(diagnostics, dict):
        raise ValueError("Summary documents must be JSON objects")
    if evaluation.get("schema_version") != 2 or diagnostics.get("schema_version") != 1:
        raise ValueError("Unsupported evaluation/diagnostic schema")
    policies = evaluation["policies"]
    if len(policies) != 4 or any(p not in {"model", "random", "land", "pass", "develop", "defend"} for p in policies):
        raise ValueError("Invalid policy profiles")
    plan = evaluation["plan"]
    if not plan:
        raise ValueError("Missing seating plan")
    seeds = list(dict.fromkeys(item["seed"] for item in plan))
    if any(type(seed) is not int for seed in seeds) or any(type(item["rotation"]) is not int or any(type(p) is not int for p in item["seat_to_profile"]) for item in plan) or plan != seating_plan(seeds):
        raise ValueError("Plan must contain four canonical rotations per seed")
    development = evaluation["development_seeds"]
    if any(type(seed) is not int for seed in development) or set(seeds) & set(development):
        raise ValueError("Evaluation/development seeds overlap or are invalid")
    checkpoint = evaluation.get("checkpoint")
    if ("model" in policies) != (checkpoint is not None):
        raise ValueError("Model/checkpoint provenance mismatch")
    if checkpoint:
        for key in ("sha256", "training_dataset_sha256"):
            if not isinstance(checkpoint.get(key), str) or not re.fullmatch("[0-9a-f]{64}", checkpoint[key]):
                raise ValueError("Invalid checkpoint hash")
        if not integer(checkpoint["epoch"], "checkpoint epoch"):
            raise ValueError("Missing trained checkpoint epoch")
    experiment = evaluation["experiment"]
    for key in ("plan", "policies", "checkpoint", "development_seeds"):
        if experiment.get(key) != evaluation[key]:
            raise ValueError("Experiment metadata disagrees with report")
    planned = {(item["seed"], item["rotation"]): item["seat_to_profile"] for item in plan}
    seen = set()
    expected = [Counter() for _ in range(4)]
    terminal, truncated, errors = 0, 0, 0
    for game in evaluation["games"]:
        if type(game["seed"]) is not int or type(game["rotation"]) is not int:
            raise ValueError("Invalid game seed/rotation")
        key = (game["seed"], game["rotation"])
        if key not in planned or key in seen or game["seat_to_profile"] != planned[key]:
            raise ValueError("Duplicate, unplanned or incorrectly seated game")
        seen.add(key)
        if any(type(game.get(flag)) is not bool for flag in ("success", "terminal", "truncated")):
            raise ValueError("Invalid completion flags")
        winners = game["winners"]
        if len(winners) != len(set(winners)) or any(type(seat) is not int or seat not in range(4) for seat in winners):
            raise ValueError("Invalid winners")
        if not game["success"]:
            errors += 1
            if winners:
                raise ValueError("Failed game has winners")
            continue
        if game["terminal"] == game["truncated"] or (game["truncated"] and winners):
            raise ValueError("Successful game needs a terminal outcome or unlabeled truncation")
        terminal += int(game["terminal"])
        truncated += int(game["truncated"])
        counts = game["decision_counts_by_seat"]
        if len(counts) != 4:
            raise ValueError("Missing decision counts by seat")
        game_decisions = 0
        for seat, counts in enumerate(counts):
            decisions = integer(counts["decisions"], "decision count")
            choices = integer(counts["choices"], "choice count")
            if choices > decisions:
                raise ValueError("Choice count exceeds decisions")
            for field in ("selected", "scopes"):
                values = counts[field]
                if not isinstance(values, dict) or sum(integer(v, field) for v in values.values()) != choices:
                    raise ValueError("Choice subtotals disagree")
            if set(counts["scopes"]) - {"priority_basic", "attack", "block"} or set(counts["selected"]) - {"pass", "skip", "land", "cast", "attack", "block"}:
                raise ValueError("Unsupported choice scope/kind")
            aggregate = expected[game["seat_to_profile"][seat]]
            aggregate.update(decisions=decisions, choices=choices, forced=decisions - choices)
            aggregate.update({"selected_" + k: v for k, v in counts["selected"].items()})
            game_decisions += decisions
        if integer(game["decisions"], "game decisions") != game_decisions:
            raise ValueError("Game/seat decision totals disagree")
    summary = summarize(evaluation["games"], policies)
    if evaluation["summary"] != summary:
        raise ValueError("Saved summary disagrees with recomputed outcomes")
    profiles = diagnostics["profiles"]
    failed_runs = Counter(game["run"] for game in evaluation["games"] if not game["success"])
    rejected_runs = Counter(item["run"] for item in diagnostics["rejected"])
    if len(profiles) != 4 or rejected_runs != failed_runs or integer(diagnostics["accepted_games"], "accepted games") != terminal + truncated:
        raise ValueError("Diagnostics are incomplete, rejected or stale")
    for index, profile in enumerate(profiles):
        if profile["profile"] != index or profile["policy"] != policies[index]:
            raise ValueError("Diagnostic profile mismatch")
        counts = profile["counts"]
        for key, value in counts.items():
            integer(value, "diagnostic count " + key)
        for key in {"decisions", "choices", "forced", *["selected_" + k for k in ("pass", "skip", "land", "cast", "attack", "block")]}:
            if counts.get(key, 0) != expected[index].get(key, 0):
                raise ValueError("Diagnostics disagree with evaluation choices")
        for kind in ("land", "cast", "attack", "block"):
            offered, selected, declined = (counts.get(kind + "_" + suffix, 0) for suffix in ("opportunities", "selected", "declined"))
            if offered != selected + declined or offered > counts.get("choices", 0) or selected != counts.get("selected_" + kind, 0):
                raise ValueError("Diagnostic opportunity counts disagree")
        opportunities = counts.get("cast_without_land_opportunities", 0)
        if opportunities > counts.get("cast_opportunities", 0) or counts.get("cast_without_land_passes", 0) > opportunities:
            raise ValueError("Invalid no-land cast-pass counts")
    missing = len(plan) - len(seen)
    warnings = []
    if missing or errors or truncated or not evaluation.get("finished_at"):
        warnings.append("Batch is incomplete or contains failed/truncated games; resolve these before comparing performance.")
    if summary["complete_seed_blocks"] < 5:
        warnings.append("Fewer than five complete independent seed blocks; uncertainty estimates are unavailable.")
    warnings.append("Summary checks cannot independently verify raw trajectories, checkpoints, or undeclared development seeds.")
    warnings.append("Imitation-policy results on vanilla Commander do not establish cEDH strength or improvement over a prior model.")
    focus = []
    for profile in profiles:
        if profile["policy"] != "model":
            continue
        counts = profile["counts"]
        if counts.get("block_opportunities", 0) and not counts.get("block_selected", 0):
            focus.append("Inspect blocking scenarios and mixed develop/defend teaching labels; the model never blocked when offered.")
        if counts.get("cast_without_land_passes", 0):
            focus.append("Inspect recorded passes when a cast was available and no land play competed; do not assume those passes were wrong.")
    if not focus:
        focus.append("Expand independent training seeds in Colab, keeping this inspected evaluation batch separate from future untouched tests.")
    if missing or errors or truncated:
        focus.insert(0, "Resume missing games and inspect failed/truncated logs before using the batch for performance comparisons.")
    return {"schema_version": 1, "integrity_passed": True,
            "batch_complete": not (missing or errors or truncated) and bool(evaluation.get("finished_at")),
            "planned": len(plan), "recorded": len(seen), "terminal": terminal,
            "truncated": truncated, "errors": errors, "missing": missing,
            "checkpoint": checkpoint, "summary": summary, "diagnostics": profiles,
            "warnings": warnings, "next_steps": focus}


def read_archive(path: Path):
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("Summary archive exceeds size limit")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != 2 or set(names) != {"evaluation.json", "diagnostics.json"}:
            raise ValueError("Require exactly evaluation.json and diagnostics.json; no extraction is performed")
        for name in names:
            if archive.getinfo(name).file_size > MAX_JSON_BYTES:
                raise ValueError("Summary JSON exceeds size limit")
        raw = {name: archive.read(name) for name in names}
    documents = {name: json.loads(data.decode("utf-8-sig")) for name, data in raw.items()}
    return raw, validate(documents["evaluation.json"], documents["diagnostics.json"])


def markdown(report):
    lines = ["# Colab Evaluation Review", "",
             f"Recorded {report['recorded']} / {report['planned']} games: {report['terminal']} terminal, "
             f"{report['truncated']} truncated, {report['errors']} errors, {report['missing']} missing.", "",
             "| Profile | Policy | Wins / Completed | Win Rate | Seed-Block 95% Range | Wins By Seat (0-3) |",
             "| --- | --- | --- | --- | --- | --- |"]
    for profile in report["summary"]["profiles"]:
        rate = "n/a" if profile["win_rate"] is None else f"{profile['win_rate']:.1%}"
        seats = ", ".join(f"{seat['wins']}/{seat['completed']}" for seat in profile["seats"])
        interval = profile["seed_block_bootstrap_95"]
        uncertainty = "n/a" if interval is None else f"{interval[0]:.1%} to {interval[1]:.1%}"
        lines.append(f"| {profile['profile']} | {profile['policy']} | {profile['wins']}/{profile['completed']} | {rate} | {uncertainty} | {seats} |")
    lines += ["", f"Complete independent seed blocks: {report['summary']['complete_seed_blocks']}.",
              "", "## Choice Behavior", ""]
    for profile in report["diagnostics"]:
        if profile["policy"] == "model":
            counts = profile["counts"]
            lines.append(f"Model profile {profile['profile']}: {counts.get('choices', 0)} meaningful choices; {counts.get('forced', 0)} forced decisions.")
            for kind in ("land", "cast", "attack", "block"):
                lines.append(f"- {kind}: selected {counts.get(kind + '_selected', 0)} / {counts.get(kind + '_opportunities', 0)} offered.")
    lines += ["", "## Limits", "", *["- " + text for text in report["warnings"]],
              "- " + report["summary"]["interval_caveat"], "", "## Next Steps", "",
              *["- " + text for text in report["next_steps"]], ""]
    return "\n".join(lines)


def import_results(source: Path, out: Path):
    raw, report = read_archive(source)
    report["archive_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    out.mkdir(parents=True, exist_ok=False)
    for name, data in raw.items():
        (out / name).write_bytes(data)
    (out / "review.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (out / "review.md").write_text(markdown(report), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = import_results(args.archive, args.out)
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as ex:
        raise SystemExit(f"Result review rejected: {ex}") from ex
    print(markdown(report))
    raise SystemExit(0 if report["batch_complete"] else 1)


if __name__ == "__main__":
    main()
