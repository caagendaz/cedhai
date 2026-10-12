# Local Forge Baseline

Installed in this workspace:

- Forge release `forge-2.0.15` (the binary reports `2.0.15-SNAPSHOT-09.28`).
- Eclipse Temurin JRE `21.0.12.1+1`, Windows x64.
- Python virtual environment `.venv`, with this package installed editable.

Downloads came from the official publishers:

- https://github.com/Card-Forge/forge/releases/tag/forge-2.0.15
- https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jre/hotspot/normal/eclipse

Archives remain in `tools/downloads`. Forge and Java are portable installations;
no global PATH or system Java installation is required. Forge's profile sets
`userDir=../forge-data` and `cacheDir=../forge-cache`, relative to `tools/forge`.
The runner disables Sentry, uses headless mode, and limits the Java heap to 2 GB.

Downloaded archive SHA256 hashes (recorded locally, not publisher attestations):

```text
forge-2.0.15.tar.bz2  4468f182b60f6ca62d89697baa208981085af744f116781af751c611826db600
java21.zip           d35f31e712f0fcf6ac5a093edc90204fbff22f720ba3950bd09d331d5e621636
```

## Run

From the project root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m cedhai.forge_cli --seed 7 --clock 120 --out runs/forge-new
.\.venv\Scripts\python.exe -m unittest discover -v
```

The default pod consists of Draconic Domination, Arcane Wizardry, Feline
Ferocity, and Vampiric Bloodlust, all bundled C17 Commander precons.
These establish engine integration; they are not cEDH evaluation baselines.

To provide decks, pass four Forge `.dck` paths:

```powershell
.\.venv\Scripts\python.exe -m cedhai.forge_cli --decks a.dck b.dck c.dck d.dck --seed 11 --out runs/custom-11
```

Forge decks use `[metadata]` with `Name=...`, `[Commander]`, and `[Main]`
sections, with counted card entries. The existing plain-text examples need
conversion and completion before use here. The runner does not certify deck
legality; validate card counts, color identity, singleton constraints, and the
current Commander ban list before scientific evaluation.

Each output directory retains exact staged decks, `stdout.log`, `stderr.log`,
and `result.json` containing the command, deck/JAR SHA256 hashes, Java version,
seed, timestamps, result, and process status. Existing run folders are never
overwritten. A draw is a completed simulation and may reflect the game clock;
inspect logs before treating it as a natural draw. Engine exceptions or missing
result lines cause the runner to exit unsuccessfully even if Java exits zero.

## Verified Source Behavior

The release's
[SimulateMatch.java](https://github.com/Card-Forge/forge/blob/forge-2.0.15/forge-gui-desktop/src/main/java/forge/view/SimulateMatch.java)
iterates every deck passed to `-d`, registers Commander players, and accepts
`-s` by setting `MyRandom` to `new Random(seed)`. The seed option is present in
the source even though the AI wiki's syntax list omits it. Source inspection
does not establish that every random decision uses this generator. Repeated
runs must be compared before claiming deterministic gameplay.

## Observed Verification

On 2026-10-11, `runs/forge-seed7-a` and `runs/forge-seed7-b` both completed
without detected engine exceptions. Feline Ferocity (seat 3) won on turn 19.
Reported game durations were 42,472 ms and 36,842 ms; startup adds roughly
30 seconds on this machine. These timings are a smoke check, not a benchmark.

After the pod header, excluding blank lines, `Game Outcome: Match Duration`,
and `Game Result:` timing lines, the two logs had identical 1,111-line event
sequences. SHA256 of each sequence joined with LF (no trailing LF):
`d21323565c2d07c27b3808081c5f93145c32aaee0cc88047083a30cf912ddf22`.
This establishes repeatability for this pod and seed only. Six Python tests
also passed using the installed virtual environment.

The CLI uses Forge's built-in AI. Its event log is useful for debugging but
does not contain structured legal-action sets, redacted observations, or
Python policy decisions. Full RL trajectories require a Java decision bridge.
