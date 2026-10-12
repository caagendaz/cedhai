# XMage Decision Bridge Spike

The prototype runs a real four-player Commander pod and lets Python choose
own-hand land plays or pass at each priority decision. Rules, shuffling,
mulligans, restrictions, card effects, and state transitions are handled by
XMage. Each selected action is checked and applied by Java, then acknowledged
back to Python. The run deliberately pauses after four individual player turns.
It does not train a model or attempt to finish a competitive game.

## Install And Run

This workspace already has the required tools installed. For a fresh clone,
use Windows PowerShell with Python 3.10+ and Windows `tar` available:

```powershell
.\scripts\install_bridge.ps1
```

The installer pins Forge 2.0.15, MageZero's XMage v0.2.0-alpha release, and
Temurin JDK 21.0.12.1+1, and verifies archive hashes before extraction. All tools
stay under `tools/`; Python dependencies stay in `.venv`. The JDK is needed
because the earlier portable JRE does not contain `javac`.

```powershell
.\.venv\Scripts\python.exe -m cedhai.run_bridge --policy random --seed 7 --out runs/bridge-new
.\.venv\Scripts\python.exe -m cedhai.run_bridge --policy pass --seed 7 --out runs/bridge-pass-new
.\.venv\Scripts\python.exe -m cedhai.run_bridge --policy land --seed 7 --out runs/bridge-land-new
```

The random policy uses the existing Python `RandomAgent`. `land` selects a
random available land when possible; `pass` always passes. Both are controls
for verifying the bridge. Use a new output folder for each invocation.
`--turns`, `--timeout`, `--jdk`, and `--engine-dir` configure the run.
The Java heap is capped at 3 GB; the spike needs no GPU.

Default decks are the four complete C17 precons bundled with Forge. Supply four
Forge `.dck` or sectioned text decks with `--decks a.dck b.dck c.dck d.dck`.
The converter moves explicit commanders into XMage's sideboard convention.
Each imported deck is validated by XMage's compiled Commander validator before
starting. This uses the release's rules/card/ban-list snapshot, not a live
Commander legality service. The tiny existing example decks will fail validation.

## Architecture

```text
Python runner
  compile the small Java harness against pinned XMage JARs
  stage decks and record software/deck hashes
  start a loopback listener on an ephemeral port
  launch Java and retain stdout/stderr

Java CommanderFreeForAll + four BridgePlayer instances
  priority -> XMage getPlayable -> filter own-hand PlayLandAbility
  decision observation -> synchronous JSONL socket -> Python agent
  selected action -> validate pending action -> XMage activateAbility/pass
  confirmed application -> Python trajectory recorder
```

The transport is a single newline-delimited JSON connection. Every decision
has a game ID, monotonic step, request ID, acting seat, and action IDs scoped to
that request. Python rejects stale, duplicate, unsupported, or mismatched
messages. Java independently rejects unavailable actions, checks the response
ID, and requires a selected land to reach the battlefield. Network failures
abort the experiment; they do not select a replacement priority action.

Output files include `trajectory.jsonl`, `result.json`, exact converted decks,
a copy of `BridgeMain.java`, compiled classes, `compile.log`, and process logs.
Metadata records the shared engine RNG seed, per-seat policy seeds, policy,
turn cap, Java version,
command, source/deck hashes, and hashes of every dependency JAR.
The database is cached in `tools/magezero/xmage/db`; run one process at a time
against this directory. First startup builds the database and may take longer.

The JSONL distinguishes `decision`, `applied`, and `finished` events. A
`decision` includes the selected response, and `applied` confirms the actual
choice and public state afterward. A turn cap produces `truncated=true` and
`terminal=false`, with no invented winner or reward. Process timeouts and
engine errors produce an unsuccessful result and retained logs.

## Source Findings

Inspected upstream XMage at `afab346e06c4960882cf148acc57754c1c50a007`, the
MageZero XMage fork at `cb7e9c6fe2dcbe2f650a77dd98a87771e730f22f`, and the
actual compiled APIs in the v0.2.0-alpha release using `javap`. The fork's HEAD
and the release are different artifacts; successful compilation and real runs
verify the release used here.

| Component | Verified reusable functionality | Limitation for this project |
| --- | --- | --- |
| Upstream XMage | Player decision overrides, playable abilities, land activation, multiplayer Commander | Needs a headless harness and policy transport; no ready Python stepping API found in inspected paths |
| MageZero fork | Prebuilt CommanderFreeForAll libraries, seeded random utilities, headless loading pattern | Existing generator creates two players; its encoder processes one player and one opponent |
| MageZero inference | HTTP `/evaluate` requests and several policy/value heads | Provides MCTS priors/value inference, not this explicit request/selected-action protocol |

Specific inspected sources:

- [Upstream PlayerImpl](https://github.com/magefree/mage/blob/afab346e06c4960882cf148acc57754c1c50a007/Mage/src/main/java/mage/players/PlayerImpl.java)
  exposes `getPlayable` and `activateAbility`. The playable API explicitly
  excludes target validation. Casts therefore cannot be exposed as complete
  legal actions without additional target, mode, payment, and choice handling.
- [Fork ComputerPlayer](https://github.com/WillWroble/mage/blob/cb7e9c6fe2dcbe2f650a77dd98a87771e730f22f/Mage.Server.Plugins/Mage.Player.AI/src/main/java/mage/player/ai/ComputerPlayer.java)
  provides overridable priority, mulligan, targeting, and choice methods.
  The bridge overrides priority and preserves its subclass when copied.
- [Fork ParallelDataGenerator](https://github.com/WillWroble/mage/blob/cb7e9c6fe2dcbe2f650a77dd98a87771e730f22f/Mage.MageZero/src/main/java/org/mage/magezero/ParallelDataGenerator.java)
  instantiates CommanderDuel/TwoPlayerDuel and configures two encoders.
- [Fork StateEncoder](https://github.com/WillWroble/mage/blob/cb7e9c6fe2dcbe2f650a77dd98a87771e730f22f/Mage.Server.Plugins/Mage.Player.AI/src/main/java/mage/player/ai/encoder/StateEncoder.java)
  holds one opponent ID and defaults `perfectInfo` to true. We do not use this
  encoder; its assumptions need redesign before hidden-information multiplayer RL.
- [Fork GameImpl](https://github.com/WillWroble/mage/blob/cb7e9c6fe2dcbe2f650a77dd98a87771e730f22f/Mage/src/main/java/mage/game/GameImpl.java)
  exposes a separate game-local RNG. Library shuffling uses it. The harness
  seeds it and `RandomUtil`; relying on `RandomUtil` alone did not reproduce hands.
- [Fork GameState](https://github.com/WillWroble/mage/blob/cb7e9c6fe2dcbe2f650a77dd98a87771e730f22f/Mage/src/main/java/mage/game/GameState.java)
  reconstructs turn lists from registered players with front insertion. Registering
  players in reverse gives the intended turn sequence 0, 1, 2, 3.

## Observations And Remaining Work

Public observations include turn/phase, active seat, and life, hand count,
library count, and battlefield count for each player. Private observations
contain only the acting player's hand. Opponent card identities and every
library's contents/order are omitted. Full battlefield/stack/command-zone
observations and visibility handling remain to be added and tested.

`legal_actions` is deliberately scoped to `own_hand_land_or_pass`. It is a
subset of the priority actions allowed by the engine, not an exhaustive Magic
action set. Mulligans, triggered choices, and other decisions use inherited
native AI handling and are not recorded as external decisions. These are
complete records of the supported bridge exchanges, not full RL trajectories.

Next expansion: serialize visible battlefield and stack state, bridge one
target-free spell and its payment choices, then cover targets/modes/optional
effects and combat. Only after those decision families are covered should the
environment claim complete action masks or train a gameplay policy. Keep
separate native baseline and external-agent adapters, and continue testing
seating, observation visibility, and reproducibility at each expansion.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v
$env:CEDHAI_TEST_XMAGE = '1'
.\.venv\Scripts\python.exe -m unittest discover -v
Remove-Item Env:CEDHAI_TEST_XMAGE
```

Ordinary discovery runs 12 fast tests and skips the real-engine test. The opt-in
test compiles and runs a real four-player pod, validates deck import, checks
all four actors, checks public/private field boundaries, verifies selected
land applications, and checks turn order and explicit truncation. It retains
its artifacts under `runs/bridge-integration-*`.

## Verified Runs

On 2026-10-11, all 13 tests passed with the real-engine test enabled.
`runs/bridge-integration-c3f893322127` and `runs/bridge-final-random-repeat`
each recorded 136 Python decisions and four confirmed land plays, with one
land on each player's battlefield. Both stopped at the configured turn cap.
The observed active seats were 0, 1, 2, 3 on turns 1, 2, 3, 4 respectively.

The 273-event trajectories matched after removing generated hand-card `id`
fields and application `card_id` fields. Canonical JSON serialization
(`sort_keys=True`, separators `(',', ':')`) of the normalized event array
produced SHA256
`56879d72fe896337d9ab1cf2112f24b0137d2672b85c10ac548d93031088052b`.
Raw UUIDs are not stable. This checks one pod/seed/action scope, not all Magic
randomness or future expanded decision families.

The same-seed `runs/bridge-final-pass` control recorded 128 decisions and zero
land plays, ending with empty battlefields. Each seat's first observed hand
matched the random-agent run. This confirms the Python policy changes the
applied game state under otherwise matching initial conditions.

Setup archive SHA256 hashes:

```text
magezero-xmage-v0.2.0-alpha.zip  c0242f186c312db81d0240d1e7479ce0f4306523ebec11d92d616a4f289926a3
jdk21.zip                      f9d6e191ab098c0d416e7d588a24420a8621cd2f4720dab2459b8b7b2d2d8b4e
```

The JDK hash also matched Adoptium's published asset checksum. The MageZero
hash was recorded from the downloaded release. Both are pinned in the installer.
