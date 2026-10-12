# Development Checkpoint: 2026-10-12

Work has resumed. The private repository is `caagendaz/cedhai`. Every feature
push includes README and Mermaid updates. Runtimes, the virtual environment,
and generated artifacts remain local under ignored `tools/`, `.venv/`, and `runs/`.

## Verified Foundation

- Forge four-player Commander baseline and seeded normalized-log comparison.
- Python-controlled XMage land/cast/attack/block decisions using legal simple
  Isamaru and Yargle Commander fixtures. Native helpers handle mana payment,
  mulligans, damage allocation, and commander-return choices.
- Acting-player private hand; public battlefield, stack, combat, commanders,
  commander damage, engine-derived features, and native terminal outcomes.
- Four exact reference cEDH lists pass Scryfall preflight with verified aliases.
  Eleven distinct recent implementations remain missing locally; upstream
  source has not been integrated/tested. Full cEDH decision coverage is future
  work. No model has been trained.

## Resumed Batch Results

`runs/curriculum-evaluation-resume/evaluation.json` contains eight sequential
Yargle games: seeds 7 and 10, four seating rotations each. Every profile visits
every seat per seed. All eight ended naturally, without errors or truncations.

| Profile | Policy | Wins / Games |
| --- | --- | --- |
| 0 | develop | 2 / 8 |
| 1 | random | 1 / 8 |
| 2 | random | 0 / 8 |
| 3 | defend | 5 / 8 |

These are exploratory controls, not evidence of superiority. Only two independent
seed blocks exist; bootstrap intervals require at least five complete blocks.

All eight runs exported to `runs/curriculum-dataset-verified`, with zero rejected
sources. The independent dataset audit passes:

| Split | Seed | Episodes | Rows | Meaningful Choices | Priority / Attack / Block |
| --- | --- | --- | --- | --- | --- |
| train | 7 | 4 | 6,226 | 370 | 262 / 81 / 27 |
| validation | 10 | 4 | 5,278 | 298 | 217 / 60 / 21 |

There are 11,504 rows and 668 meaningful choices. Forced decisions have zero
policy weight. Both splits cover every current scope, but have one independent
seed each: suitable for a training smoke test, not generalization estimates.
Random behavior is not an expert target.

`cedhai.dataset_report` checks feature dimensions/finite values, padding,
boolean masks, selected actions, labels, actor transition chains, seed-based
splits, terminal transitions, and manifest counts. Corruption tests cover split,
masked selection, transition, padding, terminal, and count failures.

Verification: 30 fast tests pass; four real-engine tests are opt-in and skipped
by default. The resumed batch verifies the latest numeric-feature extension in
eight actual games. The earlier combat suite separately passed all four engine
integration tests. No simulation remains running.

## Next Milestone

1. Implement a small masked action-scoring model and outcome-value head, seeded
   initialization, explicit configuration, and checkpoint provenance.
2. Use scripted behavior labels for a wiring smoke test, separate random
   exploration, and exclude forced choices from policy loss. This is behavior
   cloning/value prediction, not self-play reinforcement learning.
3. Test masks, checkpoint round trips, and real-game selection through the
   external `Agent` interface. Run engine games sequentially because XMage uses
   a shared H2 database. Imitation accuracy does not establish improvement.
4. Expand independent seeds and mechanics curricula before cEDH/self-play.
   Update engine/card support and decision coverage before using cEDH lists.

```powershell
.\.venv\Scripts\python.exe -m cedhai.dataset_report --dataset runs/curriculum-dataset-verified
.\.venv\Scripts\python.exe -m unittest discover -v
```
