from __future__ import annotations

import random

from .engine import Action, Observation


class RandomAgent:
    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)

    def choose_action(self, observation: Observation) -> Action:
        non_concede = [action for action in observation.legal_actions if action.id != "concede"]
        choices = non_concede or list(observation.legal_actions)
        return self._rng.choice(choices)


class BaselineAgent:
    """The same simple controls offered by the bridge, usable as external agents."""

    def __init__(self, seed: int, policy: str = "defend"):
        if policy not in {"random", "land", "pass", "develop", "defend"}:
            raise ValueError("Unknown baseline policy")
        self.policy = policy
        self.rng = random.Random(seed)

    def choose_action(self, observation: Observation) -> Action:
        actions = observation.legal_actions
        if self.policy == "random":
            return self.rng.choice(actions)
        kinds = ("land",) if self.policy == "land" else ("land", "cast", "attack", "block")
        if self.policy != "pass":
            for kind in kinds:
                choices = [action for action in actions if action.id.startswith(kind + ":")]
                if choices and (kind != "block" or self.policy == "defend"):
                    return self.rng.choice(choices)
        return next(action for action in actions if action.id in {"pass", "skip"})
