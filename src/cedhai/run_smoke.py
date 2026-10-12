from __future__ import annotations

import argparse

from .agents import RandomAgent
from .decklist import load_decklist
from .engine import SmokeEngine
from .trajectory import JsonlTrajectoryWriter


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic smoke game plumbing.")
    parser.add_argument("--decks", nargs=4, required=True, help="Exactly four Commander decklists.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", required=True, help="Output JSONL trajectory path.")
    args = parser.parse_args()

    decks = tuple(load_decklist(path) for path in args.decks)
    agents = [RandomAgent(args.seed + seat + 1) for seat in range(4)]
    engine = SmokeEngine()

    observation = engine.reset(decks, args.seed)
    with JsonlTrajectoryWriter(args.out) as writer:
        writer.write_reset(observation, args.seed)
        while True:
            action = agents[observation.seat].choose_action(observation)
            result = engine.step(action)
            writer.write_step(observation, action, result)
            if result.terminal:
                break
            if result.observation is None:
                raise RuntimeError("Non-terminal engine step did not return an observation.")
            observation = result.observation

    print(f"Wrote trajectory to {args.out}")


if __name__ == "__main__":
    main()
