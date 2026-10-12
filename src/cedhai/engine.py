from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import random

from .decklist import Decklist


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    features: dict | None = None


@dataclass(frozen=True)
class Observation:
    game_id: str
    step: int
    seat: int
    public_state: dict
    private_state: dict
    legal_actions: tuple[Action, ...]
    decision_type: str = "priority"


@dataclass(frozen=True)
class StepResult:
    observation: Observation | None
    rewards: tuple[float, ...]
    terminal: bool
    info: dict


class Agent(Protocol):
    def choose_action(self, observation: Observation) -> Action:
        """Choose one action from the observation's legal action set."""


class Engine(Protocol):
    def reset(self, decks: tuple[Decklist, ...], seed: int) -> Observation:
        """Start a game and return the first acting player's observation."""

    def step(self, action: Action) -> StepResult:
        """Apply an action chosen by the current player."""


class SmokeEngine:
    """Deterministic toy engine used to verify Python-side experiment plumbing.

    This engine is not a Magic simulator. It models a tiny contest where each
    player repeatedly chooses to advance, hold, or concede. It gives us stable
    observations, legal actions, terminal rewards, and trajectory recording while
    the real Java engine bridge is being developed.
    """

    def __init__(self, max_steps: int = 16) -> None:
        self.max_steps = max_steps
        self._rng = random.Random()
        self._decks: tuple[Decklist, ...] = ()
        self._scores: list[int] = []
        self._step = 0
        self._seat = 0
        self._game_id = ""

    def reset(self, decks: tuple[Decklist, ...], seed: int) -> Observation:
        if len(decks) != 4:
            raise ValueError("SmokeEngine requires exactly four Commander decks.")
        self._rng.seed(seed)
        self._decks = decks
        self._scores = [0, 0, 0, 0]
        self._step = 0
        self._seat = self._rng.randrange(4)
        self._game_id = f"smoke-{seed}"
        return self._observation()

    def step(self, action: Action) -> StepResult:
        if action.id not in {legal.id for legal in self._legal_actions()}:
            raise ValueError(f"Illegal action: {action.id}")

        actor = self._seat
        if action.id == "concede":
            rewards = tuple(-1.0 if seat == actor else 1.0 / 3.0 for seat in range(4))
            return StepResult(None, rewards, True, {"reason": "concession", "loser": actor})

        if action.id == "advance":
            self._scores[actor] += 2 + self._rng.randrange(3)
        elif action.id == "hold":
            self._scores[actor] += self._rng.randrange(2)

        self._step += 1
        if self._step >= self.max_steps:
            max_score = max(self._scores)
            winners = [seat for seat, score in enumerate(self._scores) if score == max_score]
            rewards = tuple(1.0 / len(winners) if seat in winners else 0.0 for seat in range(4))
            return StepResult(
                None,
                rewards,
                True,
                {"reason": "turn_cap", "scores": list(self._scores), "winners": winners},
            )

        self._seat = (self._seat + 1) % 4
        return StepResult(self._observation(), (0.0, 0.0, 0.0, 0.0), False, {})

    def _observation(self) -> Observation:
        return Observation(
            game_id=self._game_id,
            step=self._step,
            seat=self._seat,
            public_state={
                "scores": list(self._scores),
                "deck_names": [deck.name for deck in self._decks],
                "cards_loaded": [deck.total_cards for deck in self._decks],
            },
            private_state={"commander": [card.name for card in self._decks[self._seat].commanders]},
            legal_actions=self._legal_actions(),
        )

    def _legal_actions(self) -> tuple[Action, ...]:
        return (
            Action("advance", "Advance game plan"),
            Action("hold", "Hold resources"),
            Action("concede", "Concede"),
        )
