# cEDH MARL Prototype

This repository starts with a deliberately small prototype for a future
multi-agent reinforcement-learning system for competitive Commander.

The prototype reuses real Magic rules engines. Its Python-controlled XMage
curriculum currently supports four-player Commander with simple legal decks:

- load Commander decklists from common plain-text exports;
- expose observations and legal actions through a stable engine protocol;
- let an external agent choose actions;
- record complete trajectories as JSONL;
- choose supported creature casts, attackers, defending players, and blockers;
- evaluate seeded games with balanced seating and export masked training data.

Full cEDH gameplay and learned policies are not implemented yet. Native helpers
handle mulligans, mana payment, combat damage, and commander-return choices.

## Quick Start

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
.\.venv\Scripts\python.exe -m cedhai.forge_cli --seed 7 --out runs/forge-new
```

Forge and Java are installed locally under `tools/`. The Forge command runs a
real four-player Commander game using bundled C17 preconstructed decks. Use a
new output directory for each run. See `docs/forge_setup.md` for custom decks
and installation details.

For a short land/pass bridge run:

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

See [the architecture diagram](docs/architecture.md) for the decision loop and
the work leading to the first training run.

## Evaluation And Data Readiness

The latest eight-game real-engine batch completed without errors or truncations.
All eight trajectories passed export/audit: 11,504 rows and 668 meaningful
choices, with priority, attack, and block coverage in both seed-disjoint splits.
The dataset is ready for a training smoke test. No model has been trained yet.

```powershell
.\.venv\Scripts\python.exe -m cedhai.evaluate --seeds 7 10 --out runs/evaluation-new
.\.venv\Scripts\python.exe -m cedhai.learning_data --runs runs/evaluation-new/seed7-rotation0 runs/evaluation-new/seed10-rotation0 --out runs/dataset-new
.\.venv\Scripts\python.exe -m cedhai.dataset_report --dataset runs/dataset-new
```

Export all eight run folders for the complete seating-balanced dataset. Each
seed stays wholly in training or validation. The report checks feature sizes,
legal-action masks, labels, actor transitions, and manifest counts. It reports
meaningful choices by scope/policy and warns about small seed samples or absent
combat coverage. Readiness permits only a training smoke test, not a competitive
performance claim. Random/scripted choices are not optimal-action labels.

See [the curriculum](docs/curriculum.md) and [the handoff note](docs/handoff.md)
for verified results and the next training milestone. Generated trajectories
and datasets stay in ignored `runs/`; source, tests, and documentation go to GitHub.
