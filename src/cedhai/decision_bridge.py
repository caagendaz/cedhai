"""A synchronous JSONL policy protocol for a narrow XMage decision spike."""

from __future__ import annotations

import json
import random
from typing import TextIO

from .agents import RandomAgent
from .engine import Action, Observation


class DecisionSession:
    def __init__(self, writer: TextIO, seed: int, policy: str = "random"):
        if policy not in {"random", "land", "pass", "develop"}:
            raise ValueError("Unknown policy")
        self.writer = writer
        self.policy = policy
        self.agents = [RandomAgent(seed + seat) for seat in range(4)]
        self.rngs = [random.Random(seed + seat) for seat in range(4)]
        self.pending: dict | None = None
        self.decisions = 0
        self.applied_lands = 0
        self.cast_spells = 0
        self.resolved_spells = 0
        self.casts: dict[str, str] = {}
        self.finished: dict | None = None
        self.game_id: str | None = None

    def record(self, event: dict) -> None:
        self.writer.write(json.dumps(event, ensure_ascii=True) + "\n")
        self.writer.flush()

    def handle(self, event: dict) -> dict:
        if self.finished is not None:
            raise ValueError("Session already finished")
        if event.get("schema_version") not in {1, 2}:
            raise ValueError("Unsupported schema version")
        kind = event.get("event")
        if kind == "decision":
            if self.pending is not None:
                raise ValueError("Previous decision has not been applied")
            if event.get("scope") not in {"own_hand_land_or_pass", "priority_basic"}:
                raise ValueError("Unsupported action scope")
            data = event["observation"]
            seat, step = data["seat"], data["step"]
            if type(seat) is not int or seat not in range(4):
                raise ValueError("Invalid acting seat")
            if type(step) is not int or step != self.decisions:
                raise ValueError("Out-of-order decision")
            if self.game_id is None:
                self.game_id = data["game_id"]
            if data["game_id"] != self.game_id or event["request_id"] != f"{self.game_id}:{step}":
                raise ValueError("Mismatched game or request ID")
            actions = tuple(Action(**item) for item in data["legal_actions"])
            ids = [action.id for action in actions]
            if not ids or len(ids) != len(set(ids)) or "pass" not in ids:
                raise ValueError("Empty, duplicate, or missing pass actions")
            prefixes = ("land:", "cast:") if event["scope"] == "priority_basic" else ("land:",)
            if any(action_id != "pass" and not action_id.startswith(prefixes) for action_id in ids):
                raise ValueError("Unsupported action type")
            observation = Observation(**{**data, "legal_actions": actions})
            if self.policy == "pass":
                action = next(action for action in actions if action.id == "pass")
            elif self.policy in {"land", "develop"}:
                lands = [action for action in actions if action.id.startswith("land:")]
                spells = [action for action in actions if action.id.startswith("cast:")]
                choices = lands or (spells if self.policy == "develop" else [])
                action = self.rngs[seat].choice(choices) if choices else next(a for a in actions if a.id == "pass")
            else:
                action = self.agents[seat].choose_action(observation)
            response = {"request_id": event["request_id"], "action_id": action.id}
            self.pending = {"request": event, "response": response}
            self.decisions += 1
            self.record({**event, "response": response})
            return response
        if kind == "applied":
            if self.pending is None:
                raise ValueError("Applied event without a decision")
            response = self.pending["response"]
            if any(event.get(key) != response[key] for key in ("request_id", "action_id")):
                raise ValueError("Applied action does not match selected action")
            if event.get("seat") != self.pending["request"]["observation"]["seat"]:
                raise ValueError("Applied actor does not match decision")
            if response["action_id"].startswith("land:"):
                if event.get("zone") != "BATTLEFIELD":
                    raise ValueError("Land was not applied to battlefield")
                self.applied_lands += 1
            elif response["action_id"].startswith("cast:"):
                if event.get("zone") != "STACK" or not event.get("card_id"):
                    raise ValueError("Spell was not applied to stack")
                self.cast_spells += 1
                self.casts[event["request_id"]] = event["card_id"]
            self.record(event)
            self.pending = None
            return {"ok": True}
        if kind == "resolved":
            if self.pending is not None:
                raise ValueError("Resolution while a decision is pending")
            request_id = event.get("request_id")
            if self.casts.get(request_id) != event.get("card_id") or request_id not in self.casts:
                raise ValueError("Unknown or mismatched spell resolution")
            if event.get("zone") != "BATTLEFIELD":
                raise ValueError("Creature did not resolve to battlefield")
            del self.casts[request_id]
            self.resolved_spells += 1
            self.record(event)
            return {"ok": True}
        if kind == "finished":
            if self.pending is not None or self.decisions == 0:
                raise ValueError("Incomplete decision session")
            if event.get("game_id") != self.game_id or event.get("decisions") != self.decisions:
                raise ValueError("Incorrect final game or decision count")
            if event.get("applied_lands") != self.applied_lands:
                raise ValueError("Incorrect final applied land count")
            if event.get("schema_version") == 2 and (
                    event.get("cast_spells") != self.cast_spells or event.get("resolved_spells") != self.resolved_spells):
                raise ValueError("Incorrect final spell counts")
            if type(event.get("terminal")) is not bool or type(event.get("truncated")) is not bool:
                raise ValueError("Missing completion status")
            if event["terminal"] == event["truncated"]:
                raise ValueError("Expected terminal game or explicit truncation")
            self.finished = event
            self.record(event)
            return {"ok": True}
        raise ValueError("Unknown event type")
