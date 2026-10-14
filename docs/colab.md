# Colab Training

## VS Code Workflow

The official `google.colab` extension version 0.9.7 and Jupyter are installed
locally. Workspace settings enable the supported upload and Contents/Resources
views; no credentials or local compute defaults are configured.

1. Open `notebooks/colab_vscode.ipynb` in VS Code (or run `scripts/open_colab.ps1`).
2. Select Kernel > Colab > New Colab Server and choose CPU; complete Google
   sign-in when prompted. Auto Connect is also available, but check the assigned
   resources. Do not choose the local `.venv` kernel.
3. In local Explorer, select `runs/cedhai-cloud.zip` and `latest.pt`, right-click
   > Upload to Colab. Check the remote Contents view for `/content/cedhai-cloud.zip`
   and `/content/latest.pt`; adjust the first code cell if uploads are nested.
4. Run cells in order. Drive mounting requests authorization through the
   extension. The command palette also offers Colab: Mount Google Drive to Server...
   if an explicit mount cell is needed.
5. Results stay in Drive. In Colab Contents, refresh and find
   `/content/evaluation-summary.zip` (remote root), then
   right-click > Download. Checkpoints/logs are available in the same remote tree.

The extension's [official guide](https://github.com/googlecolab/colab-vscode/wiki/User-Guide)
documents kernel selection, uploads, Drive mounting, and runtime file access.
Browser-style `google.colab.files.upload/download` is not used in this variant;
the [known-issues page](https://github.com/googlecolab/colab-vscode/wiki/Known-Issues-and-Workarounds)
describes those limitations. Authentication can still use a browser, but routine
notebook execution is inside VS Code and compute remains hosted by Google.

The first code cell guards against accidental local execution. Syntax and
transfer-widget avoidance are tested; actual VS Code remote authentication,
Drive mounting, and Linux game preflight need the user's connected session.
No runtime has been provisioned or account authorized by the coding agent.

## Review The Completed Batch

Run the summary/diagnostics cell and then the ZIP export cell, not the evaluation
cell again. The updated export keeps the Drive copy and copies the ZIP to
`/content/evaluation-summary.zip`, prints its actual size, and checks that the
input JSON files exist. Refresh Colab Contents, right-click the root ZIP, and
Download. This direct-root copy avoids navigating the nested Drive directory.
If your kernel is still running the previous notebook version, rerun only the
updated export cell; the existing cloud installation/bundle is sufficient for it.

The new local command is `cedhai.review_results --archive evaluation-summary.zip
--out runs/review-new`. It needs no Java, GPU, or PyTorch and performs no games or
training. It accepts only the two expected JSON files with size limits, preserves
their bytes, recomputes the summary, checks canonical seat coverage and declared
seed separation, and matches diagnostic subtotals to per-game decision counts.
It rejects corrupt/stale summaries before creating an output directory. Valid
partial reports are written but receive an incomplete flag and nonzero exit code.

The Markdown review shows wins/rates by profile and seat, seed-block ranges,
meaningful versus forced choices, offered/selected actions, and review priorities.
Passing/skipping is not automatically a mistake. Summary-only checks cannot
verify cloud trajectories or undeclared development seeds, and even a completed
20-game vanilla curriculum batch does not establish cEDH competence. Inspect
results before launching optional retraining. The first archive was imported on
2026-10-14: 20 terminal games, model wins 3/20, no reported failures/truncations.
See [the measured review](evaluation/2026-10-14-colab.md). Expand training on
different seeds and reserve new untouched test seeds for a later checkpoint.

## Cloud-First Simulation And Evaluation

The user's PC should no longer run substantial simulation/training. Open
`notebooks/colab_simulation.ipynb` in a hosted Colab CPU runtime and upload
`runs/cedhai-cloud.zip` plus the downloaded `latest.pt`. This new bundle contains
Python, Java harness sources, legal curriculum fixtures, and the initial dataset;
it does not contain credentials or downloaded engine distributions.

The notebook installs a Linux Java 21 compiler and downloads the same pinned
MageZero engine archive used locally, verifying its SHA-256 before extraction.
The runtime must allow the apt package install and GitHub download. Then it mounts
Drive with user authorization and runs a four-turn preflight. Linux gameplay has
not been exercised here: if the preflight fails, preserve its logs and do not
claim cloud engine integration works.

The evaluation uses five fresh seeds and four seat rotations, one frozen model
profile against three `defend` controls. Declared development seeds are rejected
if reused for evaluation. The checkpoint itself does not encode all development
seeds, so freshness still depends on an honest declaration. Reports track
completed games, draws, truncations, errors, per-seat wins, and meaningful choices.
Seed-block bootstrap ranges require five complete blocks and may be degenerate
for all-zero/all-one observations; they are not proofs of the true win rate.

Drive stores input files, trajectories, logs, checkpoint snapshots, and per-game
progress. To resume after a runtime interruption, reconnect, upload the exact
same bundle/checkpoint, keep `RUN_NAME`, and rerun in order. Stop the previous
cell before retrying in the same runtime. The evaluator verifies configuration,
skips saved successful games (including documented truncations), and preserves
interrupted/failed directories as separate attempts. It never labels partial
games as completed wins/losses. Do not change seeds or weights while resuming.

The diagnostic report counts casts/attacks/blocks offered and declined. It does
not infer optimal play. The final download is `evaluation-summary.zip`; full
trajectories remain in Drive. Optional cells generate new scripted/random games
using different seeds, export data, and train on the Colab CPU. Run the optional
training cell once per new run name; evaluation seeds must remain separate.

Only training/checkpoint portability has been verified from the returned Colab
file so far. Drive persistence and full Linux simulation still require the user's
Colab session. No more local long games are launched by default.

The original training-only notebook receives audited numeric examples and Python
source, trains a small policy/value model, and saves checkpoints to Drive.
The new simulation notebook moves the rules engine to Colab too. This is scripted behavior cloning plus
outcome prediction, not self-play reinforcement learning.

## Prepared Files

- Notebook: `notebooks/colab_training.ipynb`.
- Upload archive: `runs/cedhai-colab.zip` (generated locally, not committed).
- Local dataset: `runs/curriculum-dataset-verified`.

The current archive contains source, package configuration, curriculum fixtures,
and the audited dataset. It excludes Git credentials, `.git`, engine distributions, and raw
trajectories. Each member has a SHA-256 checksum. Treat the archive as executable
code; upload only bundles you trust. Dataset/source hashes identify exact inputs;
the bundle also records the repository's HEAD revision as a reference.

## Run In Colab

1. Open [Colab](https://colab.research.google.com/), choose File > Upload notebook,
   and open `notebooks/colab_training.ipynb` from this workspace. CPU is adequate;
   GPU selection is optional through Runtime > Change runtime type.
2. Run the first cell and upload `runs/cedhai-colab.zip` when prompted.
3. Run the checksum/install/audit cells, then authorize the Drive mount.
4. Run the training cell. The default is five epochs, seed 0, hidden width 64,
   batch size 64, and only meaningful `develop`/`defend` choices. Random and
   forced decisions are excluded from both training and validation metrics.
5. The final cell displays metrics and downloads `latest.pt`. A copy and
   `metrics.json` remain in `MyDrive/cedhai/checkpoints/<run name>`.

Colab runtime storage is temporary, GPU availability is variable, and runtime
limits can change. Drive persistence and per-epoch checkpoints protect completed
epochs; a disconnected partial epoch may need rerunning. See the official
[Colab FAQ](https://research.google.com/colaboratory/faq.html).

To resume, upload the same bundle, set `RESUME` to the previous checkpoint path
in Drive, and set `EPOCHS` to a larger total count. The new run uses a fresh
directory; configuration, data, and code hashes must match. Resume includes
optimizer state and deterministic epoch shuffling. Reproduction across different
PyTorch versions, devices, or hardware is not guaranteed.

## Local Commands

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[training]"
.\.venv\Scripts\python.exe -m cedhai.colab_bundle --dataset runs/curriculum-dataset-verified --out runs/cedhai-colab.zip
.\.venv\Scripts\python.exe -m cedhai.train --dataset runs/curriculum-dataset-verified --out runs/model-new --epochs 5 --device cpu
.\.venv\Scripts\python.exe -m cedhai.play_model --checkpoint runs/model-new/latest.pt --out runs/model-game-new
```

The model scores each supplied legal action using its features and the acting
player's state, masks padded actions, and predicts that actor's final win label.
The value head describes the behavior-data outcomes; it is not an optimal
win-probability estimator. The policy combines two conflicting scripts on blocking
and has no teacher-policy conditioning, so imitation accuracy has a ceiling.
Only one training seed and one validation seed exist in the current dataset.
High imitation accuracy does not establish better play or cEDH competence.

Local verification used PyTorch 2.14.1+cpu: five training epochs, checkpoint
reload/resume tests, notebook syntax/extraction checks, and a naturally completed
seed-11 XMage pod. The model cast three creatures and attacked six times, but
lost. The user has since returned `latest.pt` from Colab: it records epoch 5 and
PyTorch 2.11.0+cpu, loads successfully locally, and matches the exact dataset and
source hashes. CUDA execution and persistent Drive contents are not independently
verified. Checkpoint files are ignored by Git, including downloads in the root.

Checkpoints use PyTorch's restricted `weights_only=True` loading rather than
arbitrary object deserialization. Still load only trusted checkpoints; see
[PyTorch loading documentation](https://docs.pytorch.org/docs/2.14/generated/torch.load.html).
