# Nightly Checkpoint: 2026-10-12

Work is paused at the user's request. All project source, reference decks,
supplied primers, tests, and documentation are committed and pushed to the
private `caagendaz/cedhai` repository. Downloaded runtimes, engine distributions,
the Python virtual environment, and generated run artifacts remain local under
ignored `tools/`, `.venv/`, and `runs/` folders.

## Verified Foundation

- Forge installed with portable Java; two four-player Commander baseline runs
  produced matching normalized logs with seed 7.
- Python-controlled XMage land/pass decisions, supported vanilla creature
  casting, native automatic mana payment, attacker/defender choices, and blocking.
- Legal simple Commander fixtures: Isamaru and Yargle and Multani.
- Public battlefield, stack, combat groups, commander locations/damage, and
  outcome flags; only the acting player's hand is exposed privately.
- Native terminal winners/rewards and explicit truncations. XMage marks winners
  `in_game=false` after completion; `has_won` is the outcome indicator.
- The full suite passed 25 tests, including four real-engine tests, before the
  latest training-feature extension. A natural Yargle pod ended on turn 35 with
  18 attacks, six casts/resolutions, and seat 0 winning.
- Four supplied cEDH lists retained exactly, with sideboards isolated. All pass
  Scryfall preflight after verified printed-name mappings. The installed engine
  still lacks 11 distinct recent implementations; upstream contains their source.

## Latest Work Saved

- Engine-derived WUBRG action colors, commander stats, and blocker-target stats.
- Per-seat scripted policies and a Python `Agent` injection interface.
- `learning_data.py`: strict episode validation, actor-specific transitions,
  numeric features, fixed action padding/masks, and seed-group data splitting.
- `evaluate.py`: four seating rotations per seed, result mapping to policy
  profiles, separate truncation/error counts, and seed-block bootstrap intervals.
- Seven new unit tests passed for data integrity, feature sizes/colors, seed
  splitting, agent injection, seating coverage, and evaluation accounting.

The eight-game evaluation attempt stopped at compilation: `getColorIdentity()`
returns `FilterMana`, not `ObjectColor`. That type mismatch has been corrected.
The latest Java sources are checked for compilation at this checkpoint; the
numeric-feature extension has not yet passed a new real-game batch. These latest
tools are saved as a checkpoint, not declared training-ready.

Final checkpoint checks: 28 fast tests passed, four opt-in real-engine tests
were skipped, and both Java harnesses compiled successfully. No new simulation
batch or training job is running.

## Resume Next

1. Run the eight-game batch with a new output folder:

   ```powershell
   .\.venv\Scripts\python.exe -m cedhai.evaluate --seeds 7 10 --out runs/curriculum-evaluation-resume
   ```

2. Verify all games, completed/truncated classifications, each profile's four
   seating positions, and engine-derived feature data. The shared XMage database
   requires sequential engine processes.
3. Export accepted episodes with `cedhai.learning_data --runs <run folders> --out
   <new dataset folder>`. Inspect rejected episodes. Seed 10 is validation and
   seed 7 training under the saved split rule; every rotation of a seed stays
   in the same split.
4. Check feature dimensions, masks, actor transitions, and source manifests on
   real data. Then begin a small masked policy/value model for this curriculum.
   The dataset's scripted choices are behavior labels, not human expertise or
   evidence of optimal play. Single-action decisions have policy weight zero.
5. Extend deck-specific decision coverage and update the engine before running
   or claiming performance on the supplied cEDH lists.

The user requests testing, committing, and pushing each completed feature.
Keep the Mermaid overview in `architecture.md` current. No training, engine
update, or additional simulation batch should run until work is resumed.
