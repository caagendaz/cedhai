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
