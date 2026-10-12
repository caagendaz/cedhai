# Colab Training

Keep Java/XMage simulations on the PC. Colab receives audited numeric examples
and Python source, trains a small policy/value model, and saves checkpoints to
Drive for local gameplay evaluation. This is scripted behavior cloning plus
outcome prediction, not self-play reinforcement learning.

## Prepared Files

- Notebook: `notebooks/colab_training.ipynb`.
- Upload archive: `runs/cedhai-colab.zip` (generated locally, not committed).
- Local dataset: `runs/curriculum-dataset-verified`.

The archive contains only Python source, package configuration, and the audited
dataset. It excludes Git credentials, `.git`, engine distributions, and raw
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
lost. Hosted notebook execution, Drive authorization, and CUDA execution still
need verification in the user's Colab account.

Checkpoints use PyTorch's restricted `weights_only=True` loading rather than
arbitrary object deserialization. Still load only trusted checkpoints; see
[PyTorch loading documentation](https://docs.pytorch.org/docs/2.14/generated/torch.load.html).
