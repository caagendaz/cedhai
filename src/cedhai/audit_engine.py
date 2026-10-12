"""Check reference decks against the installed XMage card/rules snapshot."""

import argparse
import json
from pathlib import Path
import subprocess

from .run_bridge import ROOT, export_xmage_deck


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decks", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--aliases", type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    classes = out / "classes"
    classes.mkdir()
    jdk = next((ROOT / "tools/jdk").glob("jdk-*")) / "bin"
    engine = ROOT / "tools/magezero/xmage"
    lib = str(engine / "lib/*")
    paths = []
    aliases = json.loads(args.aliases.read_text(encoding="utf-8")) if args.aliases else None
    for path in args.decks:
        target = out / (path.stem + ".txt")
        target.write_text(export_xmage_deck(path, aliases), encoding="utf-8")
        paths.append(str(target))
    source = ROOT / "java/cedhai/DeckAuditMain.java"
    with (out / "compile.log").open("w", encoding="utf-8") as log:
        subprocess.run([str(jdk / "javac.exe"), "-proc:none", "-cp", lib, "-d", str(classes), str(source)],
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=90)
    with (out / "engine.log").open("w", encoding="utf-8") as log:
        subprocess.run([str(jdk / "java.exe"), "-Xmx3g", "-Djava.awt.headless=true",
                        "--add-opens=java.base/java.lang=ALL-UNNAMED", "-cp", str(classes) + ";" + lib,
                        "cedhai.DeckAuditMain", str(out / "report.json"), *paths], cwd=engine,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
    print(json.dumps(json.loads((out / "report.json").read_text()), indent=2))


if __name__ == "__main__":
    main()
