from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cedhai.agents import RandomAgent
from cedhai.decklist import CardEntry, Decklist
from cedhai.engine import SmokeEngine
from cedhai.trajectory import JsonlTrajectoryWriter


def _deck(name: str) -> Decklist:
    return Decklist(
        name=name,
        cards=(
            CardEntry("Example Commander", 1, "commander"),
            CardEntry("Sol Ring", 1, "main"),
        ),
    )


class SmokeEngineTests(unittest.TestCase):
    def test_deterministic_game_records_complete_trajectory(self) -> None:
        decks = tuple(_deck(f"deck{idx}") for idx in range(4))
        first = self._run(decks, 11)
        second = self._run(decks, 11)

        self.assertEqual(first, second)
        self.assertEqual(first[0]["event"], "reset")
        self.assertTrue(first[-1]["result"]["terminal"])

    def test_requires_four_decks(self) -> None:
        with self.assertRaises(ValueError):
            SmokeEngine().reset((_deck("one"),), seed=1)

    def _run(self, decks: tuple[Decklist, ...], seed: int) -> list[dict]:
        engine = SmokeEngine(max_steps=4)
        agents = [RandomAgent(seed + seat) for seat in range(4)]
        observation = engine.reset(decks, seed)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trajectory.jsonl"
            with JsonlTrajectoryWriter(path) as writer:
                writer.write_reset(observation, seed)
                while True:
                    action = agents[observation.seat].choose_action(observation)
                    result = engine.step(action)
                    writer.write_step(observation, action, result)
                    if result.terminal:
                        break
                    assert result.observation is not None
                    observation = result.observation
            return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


if __name__ == "__main__":
    unittest.main()
