# cEDH MARL Prototype

This repository starts with a deliberately small prototype for a future
multi-agent reinforcement-learning system for competitive Commander.

The prototype does not implement Magic rules. It provides the Python-side
interfaces needed to connect to a real rules engine later:

- load Commander decklists from common plain-text exports;
- expose observations and legal actions through a stable engine protocol;
- let an external agent choose actions;
- record complete trajectories as JSONL;
- run deterministic smoke experiments with a seed.

## Quick Start

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe -m cedhai.forge_cli --seed 7 --out runs/forge-new
```

Forge and Java are installed locally under `tools/`. The Forge command runs a
real four-player Commander game using bundled C17 preconstructed decks. Use a
new output directory for each run. See `docs/forge_setup.md` for custom decks
and installation details.

The next spike now connects Python agents to real XMage priority decisions:

```powershell
.\.venv\Scripts\python.exe -m cedhai.run_bridge --policy random --seed 7 --out runs/bridge-new
```

It runs four validated Commander decks with Python choosing land plays or pass,
and records each decision and confirmed application. See
[`docs/decision_bridge.md`](docs/decision_bridge.md) for reproducible installation,
source findings, tests, and the remaining work toward full gameplay control.

The original `cedhai.run_smoke` module is a synthetic interface test, not a
Magic simulation. The tiny decklists in `examples/decks` are parser fixtures,
not complete legal Commander decks.

Open `docs/research.md` for the engine comparison and phased implementation
plan.
