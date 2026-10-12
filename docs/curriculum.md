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
