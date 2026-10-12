from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json

from .engine import Action, Observation, StepResult


class JsonlTrajectoryWriter:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("w", encoding="utf-8")

    def write_reset(self, observation: Observation, seed: int) -> None:
        self._write({"event": "reset", "seed": seed, "observation": asdict(observation)})

    def write_step(self, observation: Observation, action: Action, result: StepResult) -> None:
        self._write(
            {
                "event": "step",
                "observation": asdict(observation),
                "action": asdict(action),
                "result": asdict(result),
            }
        )

    def close(self) -> None:
        self._handle.close()

    def __enter__(self) -> "JsonlTrajectoryWriter":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _write(self, payload: dict) -> None:
        self._handle.write(json.dumps(payload, sort_keys=True) + "\n")
        self._handle.flush()
