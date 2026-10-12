"""Run Forge's built-in AI; this CLI does not expose agent decisions."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


RESULT = re.compile(
    r"^Game Result: Game (?P<game>\d+) (?:"
    r"ended in (?P<duration>\d+) ms\. (?P<winner>.+) has won!|"
    r"ended in a Draw! Took (?P<draw_duration>\d+) ms\.)$",
    re.MULTILINE,
)
PRECONS = (
    "C17 - Draconic Domination.dck",
    "C17 - Arcane Wizardry.dck",
    "C17 - Feline Ferocity.dck",
    "C17 - Vampiric Bloodlust.dck",
)


def parse_results(log: str) -> list[dict]:
    return [
        {
            "game": int(match["game"]),
            "winner": match["winner"],
            "draw": match["winner"] is None,
            "duration_ms": int(match["duration"] or match["draw_duration"]),
        }
        for match in RESULT.finditer(log)
    ]


def run_forge(
    java: Path, jar: Path, decks: list[Path], out: Path,
    seed: int = 7, clock: int = 120,
) -> dict:
    java, jar = java.resolve(), jar.resolve()
    decks = [deck.resolve() for deck in decks]
    if len(decks) != 4:
        raise ValueError("Exactly four Commander decks are required")
    for path in (java, jar, *decks):
        if not path.is_file():
            raise FileNotFoundError(path)
    if any(deck.suffix.lower() != ".dck" for deck in decks):
        raise ValueError("Forge requires .dck decks with [Commander] and [Main] sections")
    if clock <= 0:
        raise ValueError("Clock must be positive")

    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    staged = out / "decks"
    staged.mkdir()
    deck_records = []
    for seat, deck in enumerate(decks, 1):
        content = deck.read_bytes()
        filename = f"seat{seat}.dck"
        (staged / filename).write_bytes(content)
        deck_records.append({
            "seat": seat, "source": str(deck), "file": filename,
            "sha256": hashlib.sha256(content).hexdigest(),
        })
    command = [
        str(java), "-Xmx2g", "-Djava.awt.headless=true", "-Dsentry.enabled=false",
        "-jar", str(jar), "sim", "-d",
        *[record["file"] for record in deck_records],
        "-D", str(staged), "-f", "Commander", "-n", "1",
        "-s", str(seed), "-c", str(clock),
    ]
    env = os.environ.copy()
    env["SENTRY_ENABLED"] = "false"
    metadata = {
        "schema_version": 1, "engine": "Forge", "policy": "Forge built-in AI",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed, "clock_seconds": clock, "command": command,
        "cwd": str(jar.parent), "decks": deck_records,
        "jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(),
        "java_version": subprocess.check_output(
            [str(java), "-version"], stderr=subprocess.STDOUT, text=True,
        ).strip(),
    }
    with (out / "stdout.log").open("w", encoding="utf-8") as stdout, \
            (out / "stderr.log").open("w", encoding="utf-8") as stderr:
        try:
            process = subprocess.run(
                command, cwd=jar.parent, env=env, stdout=stdout, stderr=stderr,
                timeout=clock + 180, check=False,
            )
            metadata["returncode"] = process.returncode
        except subprocess.TimeoutExpired:
            metadata["returncode"] = None
            metadata["error"] = "Process exceeded startup plus game time budget"
    log = (out / "stdout.log").read_text(encoding="utf-8", errors="replace")
    errors = (out / "stderr.log").read_text(encoding="utf-8", errors="replace")
    metadata["results"] = parse_results(log)
    metadata["engine_error_detected"] = bool(re.search(
        r"Exception|StackOverflowError|OutOfMemoryError|Could not load deck|No deck found",
        log + errors,
    ))
    metadata["success"] = (
        metadata["returncode"] == 0 and len(metadata["results"]) == 1
        and not metadata["engine_error_detected"]
    )
    metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
    (out / "result.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forge-dir", type=Path, default=Path("tools/forge"))
    parser.add_argument("--java", type=Path)
    parser.add_argument("--decks", type=Path, nargs=4)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--clock", type=int, default=120)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    java = args.java or next(Path("tools/java").glob("*/bin/java.exe"), None)
    if java is None:
        parser.error("Portable Java missing; specify --java")
    jars = list(args.forge_dir.glob("forge-gui-desktop-*-jar-with-dependencies.jar"))
    if len(jars) != 1:
        parser.error("Expected one Forge desktop JAR in --forge-dir")
    decks = args.decks or [
        args.forge_dir / "res/adventure/Realm of Legends/decks/starter/commanderprecon" / name
        for name in PRECONS
    ]
    result = run_forge(java, jars[0], decks, args.out, args.seed, args.clock)
    print(json.dumps({key: result[key] for key in ("success", "seed", "results")}, indent=2))
    raise SystemExit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
