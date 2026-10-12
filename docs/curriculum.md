# First Learning Curriculum

Reference cEDH lists are stored under `examples/decks/reference` and audited
separately. They are not substituted with simplified cards. Current engine
support gaps are in `docs/primers/reference_notes.md`.

`--mode basic` runs legal, intentionally simple Commander decks with basic
lands and a strict set of supported vanilla creatures. The deck gate rejects
other cards instead of pretending to provide complete cEDH control.

The first supported creature set is Isamaru, Hound of Konda; Savannah Lions;
Elite Vanguard; Grizzly Bears; Runeclaw Bear; and Yargle and Multani. These
avoid target, mode, variable-cost, and triggered-effect decisions. This is a
mechanics curriculum, not an optimized deck or cEDH evaluation baseline.

Python selects lands and creature spells from XMage's playable abilities,
including commander casting. XMage's existing automatic tapping pays mana;
manual selection among payment plans is not a Python decision yet. A spell's
`applied` event confirms its stack entry. A separate `resolved` event confirms
its battlefield entry. Casts and resolutions have separate counters.

Protocol schema 2 adds structured action features and richer public battlefield,
stack, player-life, mana-pool, and in-game status observations. Face-down
battlefield objects omit printed identity. Own-hand observations remain private;
opponent hands and library identities are never serialized. Full hidden-information
coverage for arbitrary cards remains outside this curriculum.

```powershell
.\.venv\Scripts\python.exe -m cedhai.run_bridge --mode basic --policy develop --decks examples/decks/curriculum/isamaru.txt examples/decks/curriculum/isamaru.txt examples/decks/curriculum/isamaru.txt examples/decks/curriculum/isamaru.txt --turns 4 --out runs/casting-new
```

`develop` prioritizes a legal land, then a supported creature, then pass.
`land` selects lands and otherwise passes. `random` selects from the offered
actions. `pass` provides a control. Schema 1 remains accepted for replay/tests.

The verified first run recorded 152 decisions, four land plays, four commander
casts, and four resolutions. Training should wait until combat, natural game
termination, correct rewards, replay extraction, and held-out seeded evaluation
are verified. Winota triggers, ninjutsu, tutors, storm, and stack interaction
will need separate staged curricula after the first model learns these basics.

## Combat Verification

The basic mode now asks Python to declare each eligible attacker and choose a
defending player, then to select a legal attacker for each eligible blocker or
skip blocking. XMage validates declarations and handles damage/state-based actions.
`develop` attacks when possible and skips blocks; `defend` also blocks when possible.
These are simple controls, not strategic reference policies.

Public observations include combat groups, commander locations, accumulated
commander damage to each seat, and explicit win/loss/draw flags. `in_game` means
a player can still participate: XMage sets it false for the winner too after a
game finishes. Evaluation uses `has_won` and the engine's winners list.

A verified four-Yargle pod with seed 7 ended naturally on individual player turn
35, with 1,260 decisions, 18 attacks, six casts/resolutions, and seat 0 winning.
Its terminal rewards were `[1, 0, 0, 0]`. A separate Isamaru integration run
verified Python-controlled blocking. All 25 tests passed on 2026-10-12,
including four real-engine tests.

```powershell
.\.venv\Scripts\python.exe -m cedhai.run_bridge --mode basic --policy develop --decks examples/decks/curriculum/yargle.txt examples/decks/curriculum/yargle.txt examples/decks/curriculum/yargle.txt examples/decks/curriculum/yargle.txt --turns 100 --out runs/combat-new
```

Natural wins receive 1 for engine winners and 0 for other seats. Natural draws
receive all-zero rewards. A turn cap is an explicit truncation and has no terminal
reward label. Native mulligans, automatic mana payment, damage allocation, and
commander-return replacement choices remain fixed environment helpers. The
curriculum trains high-level decisions under those helpers, not full Magic control.
