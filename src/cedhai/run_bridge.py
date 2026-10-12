"""Compile and run the four-player XMage land/pass bridge."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import socketserver
import subprocess
import threading

from .decision_bridge import DecisionSession
from .decklist import load_decklist
from .forge_cli import PRECONS


ROOT = Path(__file__).resolve().parents[2]
MAX_MESSAGE_BYTES = 1024 * 1024


def export_xmage_deck(source: Path) -> str:
    """Convert a Forge deck or our sectioned text format to XMage text import."""
    if source.suffix.lower() == ".dck":
        sections: dict[str, list[str]] = {"main": [], "commander": []}
        section = ""
        for raw in source.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].lower()
            elif line and section in sections:
                match = re.fullmatch(r"(\d+)\s+(.+?)(?:\|.*)?", line)
                if not match or int(match[1]) <= 0:
                    raise ValueError(f"Invalid Forge card line: {line}")
                name = match[2].removesuffix("+")
                sections[section].append(f"{match[1]} {name}")
            elif line and section not in {"metadata", "main", "commander"}:
                raise ValueError(f"Unsupported Forge section: {section}")
        if not sections["main"] or not sections["commander"]:
            raise ValueError("Deck must have main cards and commanders")
    else:
        deck = load_decklist(source)
        sections = {
            name: [f"{card.count} {card.name}" for card in deck.cards if card.section == name]
            for name in ("main", "commander")
        }
        if not sections["commander"]:
            raise ValueError("Text deck requires an explicit Commander section")
    return "\n".join([*sections["main"], "//sideboard", *sections["commander"]]) + "\n"


def run_bridge(jdk: Path, engine_dir: Path, decks: list[Path], out: Path,
               seed: int, policy: str, turns: int, timeout: int) -> dict:
    jdk, engine_dir, out = jdk.resolve(), engine_dir.resolve(), out.resolve()
    if len(decks) != 4 or turns < 1 or timeout < 1:
        raise ValueError("Require four decks and positive turn/time limits")
    out.mkdir(parents=True, exist_ok=False)
    classes = out / "classes"
    classes.mkdir()
    staged = out / "decks"
    staged.mkdir()
    paths = []
    records = []
    for seat, source in enumerate(decks):
        source = source.resolve()
        path = staged / f"seat{seat}.txt"
        path.write_text(export_xmage_deck(source), encoding="utf-8")
        paths.append(str(path))
        records.append({"seat": seat, "source": str(source),
                        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                        "staged_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    bin_dir = jdk / "bin"
    java, javac = bin_dir / "java.exe", bin_dir / "javac.exe"
    lib = str(engine_dir / "lib" / "*")
    source = ROOT / "java/cedhai/BridgeMain.java"
    (out / "BridgeMain.java").write_bytes(source.read_bytes())
    compile_command = [str(javac), "-proc:none", "-encoding", "UTF-8", "-cp", lib, "-d", str(classes), str(source)]
    with (out / "compile.log").open("w", encoding="utf-8") as log:
        subprocess.run(compile_command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=90)
    metadata = {"schema_version": 1, "engine": "MageZero XMage v0.2.0-alpha",
                "scope": "own_hand_land_or_pass", "seed": seed, "policy": policy,
                "policy_seeds": [seed + seat for seat in range(4)],
                "max_turns": turns, "decks": records, "compile_command": compile_command,
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "library_jars": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted((engine_dir / "lib").glob("*.jar"))},
                "java_version": subprocess.check_output([str(java), "-version"],
                                stderr=subprocess.STDOUT, text=True).strip()}
    errors: list[str] = []
    with (out / "trajectory.jsonl").open("w", encoding="utf-8") as trajectory:
        session = DecisionSession(trajectory, seed, policy)

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.connection.settimeout(timeout)
                try:
                    while True:
                        line = self.rfile.readline(MAX_MESSAGE_BYTES + 1)
                        if not line:
                            break
                        if len(line) > MAX_MESSAGE_BYTES or not line.endswith(b"\n"):
                            raise ValueError("Oversized or incomplete bridge message")
                        reply = session.handle(json.loads(line))
                        self.wfile.write((json.dumps(reply) + "\n").encode("utf-8"))
                        self.wfile.flush()
                except Exception as ex:
                    errors.append(str(ex))
                    session.record({"event": "error", "message": str(ex)})
                    try:
                        self.wfile.write((json.dumps({"error": str(ex)}) + "\n").encode("utf-8"))
                        self.wfile.flush()
                    except OSError:
                        pass

        server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        command = [str(java), "-Xmx3g", "-Djava.awt.headless=true",
                   "--add-opens=java.base/java.lang=ALL-UNNAMED", "-cp", str(classes) + ";" + lib,
                   "cedhai.BridgeMain", str(server.server_address[1]), str(seed), str(turns), *paths]
        metadata.update({"command": command, "cwd": str(engine_dir)})
        try:
            with (out / "stdout.log").open("w", encoding="utf-8") as stdout, \
                    (out / "stderr.log").open("w", encoding="utf-8") as stderr:
                try:
                    process = subprocess.run(command, cwd=engine_dir, stdout=stdout, stderr=stderr,
                                             timeout=timeout, check=False)
                    metadata["returncode"] = process.returncode
                except subprocess.TimeoutExpired:
                    metadata["returncode"] = None
                    errors.append("Java process exceeded run timeout")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        log_text = "\n".join((out / name).read_text(encoding="utf-8", errors="replace")
                             for name in ("stdout.log", "stderr.log"))
        if re.search(r"Exception|StackOverflowError|OutOfMemoryError|\bERROR\b", log_text):
            errors.append("Engine error detected; inspect stdout.log and stderr.log")
        metadata.update({"decisions": session.decisions, "applied_lands": session.applied_lands,
                         "completion": session.finished, "errors": errors,
                         "success": metadata["returncode"] == 0 and session.finished is not None and not errors})
    (out / "result.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jdk", type=Path)
    parser.add_argument("--engine-dir", type=Path, default=ROOT / "tools/magezero/xmage")
    parser.add_argument("--decks", type=Path, nargs=4)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--policy", choices=("random", "land", "pass"), default="random")
    parser.add_argument("--turns", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    jdk = args.jdk or next((ROOT / "tools/jdk").glob("jdk-*"), None)
    if jdk is None:
        parser.error("Portable JDK missing; specify --jdk")
    decks = args.decks or [ROOT / "tools/forge/res/adventure/Realm of Legends/decks/starter/commanderprecon" / name
                           for name in PRECONS]
    result = run_bridge(jdk, args.engine_dir, decks, args.out, args.seed, args.policy, args.turns, args.timeout)
    print(json.dumps({key: result[key] for key in ("success", "decisions", "applied_lands", "errors")}, indent=2))
    raise SystemExit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
