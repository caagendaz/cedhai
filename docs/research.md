# Engine Feasibility Notes

Date: 2026-10-11

Follow-up source inspection and a verified four-player external-decision spike
are documented in [decision_bridge.md](decision_bridge.md). The current code
reuses MageZero's prebuilt XMage libraries with a small independent Java harness;
it does not require an engine fork for the land/pass boundary. A full fork may
still be needed for broader decisions, throughput, and rules fixes.

## Summary Recommendation

Use XMage as the primary long-term rules engine, with MageZero as the closest
existing proof that XMage can be adapted into a learning environment. Use Forge
only as a near-term baseline simulator for AI-vs-AI deck smoke tests and coarse
deck-optimization experiments.

The initial prototype provided Python-side deck loading, observation/action
interfaces, seeded agents, and trajectory recording. The standalone Java
harness now applies real land/pass actions selected over local IPC. The next
Java milestone is to cover more decision families and visible game state.

## XMage

Reusable functionality:

- Full rules-enforcement engine with a server/client architecture.
- Official support for multiplayer games, Commander, and AI opponents.
- Server-side hidden-information enforcement.
- Large existing test suite and active card implementation work.
- Existing AI code paths and test mode that can be inspected and adapted.

Suitability:

- Best fit for accurate four-player cEDH simulation.
- Best fit for preserving hidden information correctly.
- Likely best long-term source of legal-action enumeration because the server
  already controls player decisions.

Blockers:

- No documented Python/Gym API for stepping games.
- External-agent control likely requires Java-side changes in player decision
  handlers.
- Throughput and memory usage are likely major constraints for self-play.
- Multiplayer action serialization and observation redaction need careful design.

## Forge

Reusable functionality:

- Headless `sim` mode for AI matches from the command line.
- Commander format support in simulation mode.
- Tournament-style batch simulation and result logging.
- Easier first contact for deck-vs-deck smoke testing.

Suitability:

- Good for near-term automated baselines and deck-optimization loops.
- Weaker fit for RL because the public CLI runs Forge's own AI rather than an
  external Python policy.

Blockers:

- AI is heuristic and documented as weak for combo decks.
- No documented external-agent step API from the public simulation CLI.
- Legal-action observations and per-decision control would require Java
  integration work similar to XMage, but with less direct RL precedent.

## MageZero

Reusable functionality:

- Python training pipeline, CLI, config structure, and data-generation flow.
- XMage fork with MageZero-specific Java modules for vectorization and MCTS.
- Local inference server pattern for Java-to-Python policy/value calls.
- Documentation for single-machine training with 8 GB+ NVIDIA VRAM.

Suitability:

- Most relevant existing RL framework.
- Strongest starting point for a two-player deck-local learner.
- Useful reference for IPC, data formats, and XMage-side hooks.

Blockers:

- Current public docs describe deck-local training, not four-player Commander.
- Public configs are two-player (`player_a`, `player_b`) rather than pod-based.
- Still alpha; the XMage fork and data format must be inspected before betting
  the whole project on it.
- cEDH-specific combo play and multiplayer politics are not solved by the
  framework.

## Recommended Architecture

```text
Python package
  deck_loader        parse and normalize decklists
  env_protocol       observations, legal actions, terminal transitions
  agents             random, scripted combo, learned policy adapters
  trajectory_store   JSONL/HDF5/parquet recorders
  evaluation         seating, seeds, win-rate confidence intervals
  training           self-play and replay-buffer orchestration

Java rules engine adapter
  XMage fork/plugin
    create Commander table
    load four decklists
    seed shuffle/random sources where possible
    enumerate legal player decisions
    redact observations by player
    call Python policy server or IPC client
    emit complete trajectories

Optional baseline adapter
  Forge CLI runner
    run headless AI-vs-AI simulations
    parse result logs
    use only for baseline/deck smoke tests until step control exists
```

## Phased Plan

1. Python interface skeleton, deterministic smoke engine, trajectory recorder,
   and tests. This repository implements that phase.
2. Forge CLI baseline runner: run installed Forge against real Commander decks,
   parse winners, and store reproducible metadata. This does not provide RL
   actions, but gives immediate deck-test automation.
3. XMage code inspection spike (implemented): locate player decision APIs, AI player classes,
   test-mode harness, random/seeding points, and deck loading. Produce a tiny
   Java proof that logs legal actions for one decision. The spike now logs and
   applies own-hand land/pass decisions in four-player Commander.
4. XMage external-agent bridge (land/pass implemented): local HTTP/gRPC/socket bridge from Java to
   Python with request/response schemas matching `cedhai.engine`.
5. Four-player Commander harness (fixed seating implemented): pod creation, seating randomization, hidden
   observation redaction, terminal scoring, and trajectory persistence.
6. Foundational agents: random, pass-priority baseline, scripted combo
   execution tests, and behavior-cloned policy from heuristic traces.
7. Self-play: population/evaluation split, fixed baselines, uncertainty tracking,
   replay buffers, and GPU training on RTX 3070-scale batches.
8. Deck optimization: legal substitution proposals, fixed-agent evaluation,
   confidence intervals, and rollback criteria.
