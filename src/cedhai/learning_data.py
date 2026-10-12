"""Validate completed curriculum episodes and export numeric policy/value examples."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


SCOPES = ("priority_basic", "attack", "block")
KINDS = ("pass", "land", "cast", "attack", "block", "skip")
STATE_SIZE = 104
ACTION_SIZE = 21
MAX_ACTIONS = 32


def encode_state(observation: dict, scope: str) -> list[float]:
    if scope not in SCOPES:
        raise ValueError("Unsupported training decision scope")
    seat = observation["seat"]
    state = observation["public_state"]
    vector = [state["turn"] / 100.0]
    vector += [float(scope == item) for item in SCOPES]
    active = (state["active_seat"] - seat) % 4
    vector += [float(active == i) for i in range(4)]
    players = {p["seat"]: p for p in state["players"]}
    for relative in range(4):
        index = (seat + relative) % 4
        player = players[index]
        board = [p for p in state["battlefield"] if p["controller_seat"] == index]
        creatures = [p for p in board if p.get("creature")]
        damage = [c["damage_to_seats"][index] for c in state["commanders"]]
        vector += [player["life"] / 40.0, player["hand_count"] / 10.0,
                   player["library_count"] / 100.0, float(player["in_game"]),
                   len(board) / 30.0, sum(not p["tapped"] for p in creatures) / 10.0,
                   sum(p["power"] for p in creatures) / 40.0,
                   sum(p["toughness"] for p in creatures) / 40.0,
                   max(damage, default=0) / 21.0]
        for color in range(5):
            vector.append(sum(p.get("land") and not p["tapped"] and p["colors"][color] for p in board) / 20.0)
        # Commander location remains visible even when it is not on the battlefield.
        own = [c for c in state["commanders"] if c["owner_seat"] == index]
        vector += [float(any(c["zone"] == "COMMAND" for c in own))]
        vector += [max((c[key] for c in own), default=0) / scale
                   for key, scale in (("mana_value", 10.0), ("power", 40.0), ("toughness", 40.0))]
        vector += [float(any(c["colors"][color] for c in own)) for color in range(5)]
    hand = observation["private_state"]["hand"]
    vector += [sum(c["mana_value"] for c in hand) / 100.0,
               max((c["mana_value"] for c in hand), default=0) / 10.0,
               len(state["stack"]) / 10.0, len(state["combat"]) / 10.0]
    if len(vector) != STATE_SIZE or not all(math.isfinite(x) for x in vector):
        raise ValueError("Invalid state feature vector")
    return vector


def encode_action(action: dict, seat: int) -> list[float]:
    kind = action["id"].split(":", 1)[0]
    if kind not in KINDS:
        raise ValueError("Unknown training action kind")
    features = action.get("features") or {}
    colors = features.get("colors", [False] * 5)
    if kind in {"land", "cast"} and "colors" not in features:
        raise ValueError("Old trajectory lacks engine-derived action colors")
    if len(colors) != 5:
        raise ValueError("Expected WUBRG color features")
    target = features.get("target_seat")
    if target is not None and (type(target) is not int or target not in range(4)):
        raise ValueError("Invalid action target seat")
    relative = (target - seat) % 4 if target is not None else -1
    vector = [float(kind == item) for item in KINDS]
    vector += [features.get("mana_value", 0) / 10.0, features.get("power", 0) / 40.0,
               features.get("toughness", 0) / 40.0]
    vector += [float(value) for value in colors]
    vector += [float(relative == i) for i in range(4)]
    vector += [features.get("target_power", 0) / 40.0, features.get("target_toughness", 0) / 40.0,
               features.get("target_mana_value", 0) / 10.0]
    if len(vector) != ACTION_SIZE or not all(math.isfinite(x) for x in vector):
        raise ValueError("Invalid action feature vector")
    return vector


def load_episode(path: Path) -> tuple[dict, list[dict]]:
    metadata = json.loads((path / "result.json").read_text(encoding="utf-8"))
    if not metadata.get("success") or metadata.get("mode") != "basic":
        raise ValueError("Require a successful basic-curriculum run")
    if metadata.get("observation_features_version") != 1:
        raise ValueError("Missing compatible observation features")
    trace = (path / "trajectory.jsonl").read_bytes()
    events = [json.loads(line) for line in trace.decode("utf-8").splitlines()]
    if not events or events[-1].get("event") != "finished":
        raise ValueError("Missing completed trajectory")
    finished = events[-1]
    if not finished.get("terminal") or finished.get("truncated"):
        raise ValueError("Truncated episodes do not have training outcome labels")
    if metadata.get("completion") != finished:
        raise ValueError("Metadata and trajectory outcomes disagree")
    winners = finished["winners"]
    if len(winners) != len(set(winners)) or any(type(s) is not int or s not in range(4) for s in winners):
        raise ValueError("Invalid winners")
    expected = [1.0 if seat in winners else 0.0 for seat in range(4)]
    if finished.get("rewards") != expected:
        raise ValueError("Outcome reward mismatch")
    decisions = []
    pending = None
    unresolved = {}
    counts = {"land": 0, "cast": 0, "attack": 0, "block": 0, "resolved": 0}
    for event in events[:-1]:
        if event.get("schema_version") != 2:
            raise ValueError("Unsupported trajectory schema")
        kind = event.get("event")
        if kind == "decision":
            if pending is not None:
                raise ValueError("Decision without prior application")
            observation = event["observation"]
            step = len(decisions)
            if observation["step"] != step or event["request_id"] != f"{finished['game_id']}:{step}":
                raise ValueError("Out-of-order decision")
            actions = observation["legal_actions"]
            ids = [action["id"] for action in actions]
            if not ids or len(ids) != len(set(ids)) or len(ids) > MAX_ACTIONS:
                raise ValueError("Invalid or oversized action mask")
            if event["response"].get("request_id") != event["request_id"] or event["response"]["action_id"] not in ids:
                raise ValueError("Unavailable or mismatched selected action")
            decisions.append(event)
            pending = event
        elif kind == "applied":
            if pending is None or any(event.get(k) != pending["response"][k] for k in ("request_id", "action_id")):
                raise ValueError("Application does not match decision")
            if event.get("seat") != pending["observation"]["seat"]:
                raise ValueError("Application actor mismatch")
            action_kind = event["action_id"].split(":", 1)[0]
            if action_kind in counts:
                expected_zone = "STACK" if action_kind == "cast" else "BATTLEFIELD"
                if event.get("zone") != expected_zone:
                    raise ValueError("Incorrect applied action zone")
                counts[action_kind] += 1
            if action_kind == "cast":
                unresolved[event["request_id"]] = event["card_id"]
            pending = None
        elif kind == "resolved":
            if pending is not None or unresolved.get(event.get("request_id")) != event.get("card_id"):
                raise ValueError("Unmatched spell resolution")
            if event.get("zone") != "BATTLEFIELD":
                raise ValueError("Incorrect creature resolution zone")
            del unresolved[event["request_id"]]
            counts["resolved"] += 1
        else:
            raise ValueError("Incomplete or unexpected trajectory event")
    if pending is not None or unresolved or len(decisions) != finished["decisions"] or not decisions:
        raise ValueError("Incomplete decision sequence")
    for key, count in counts.items():
        outcome_key = {"land": "applied_lands", "cast": "cast_spells", "resolved": "resolved_spells",
                       "attack": "attacks", "block": "blocks"}[key]
        if finished.get(outcome_key) != count:
            raise ValueError("Final action counters disagree")
    episode_id = hashlib.sha256(trace).hexdigest()
    return {**metadata, "episode_id": episode_id}, decisions


def examples(path: Path) -> tuple[dict, list[dict]]:
    metadata, decisions = load_episode(path)
    rows = []
    previous = {}
    policies = metadata["seat_policies"]
    for event in decisions:
        observation = event["observation"]
        seat = observation["seat"]
        state = encode_state(observation, event["scope"])
        actions = observation["legal_actions"]
        vectors = [encode_action(action, seat) for action in actions]
        selected = [action["id"] for action in actions].index(event["response"]["action_id"])
        row = {"episode_id": metadata["episode_id"], "seed": metadata["seed"], "seat": seat,
               "step": observation["step"], "policy": policies[seat], "scope": event["scope"],
               "state": state, "actions": vectors + [[0.0] * ACTION_SIZE for _ in range(MAX_ACTIONS - len(vectors))],
               "action_mask": [True] * len(vectors) + [False] * (MAX_ACTIONS - len(vectors)),
               "selected_index": selected, "next_state": None, "terminated": True,
               "choice_count": len(actions), "policy_weight": float(len(actions) > 1),
               "reward": metadata["completion"]["rewards"][seat],
               "outcome_target": metadata["completion"]["rewards"][seat],
               "split": "validation" if metadata["seed"] % 5 == 0 else "train"}
        if seat in previous:
            previous[seat].update(next_state=state, terminated=False, reward=0.0)
        rows.append(row)
        previous[seat] = row
    return metadata, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", nargs="+", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = {"schema_version": 1, "state_size": STATE_SIZE, "action_size": ACTION_SIZE,
                "max_actions": MAX_ACTIONS, "split_rule": "seed % 5 == 0 means validation",
                "episodes": [], "rejected": [], "rows": 0}
    seen = set()
    with (args.out / "examples.jsonl").open("w", encoding="utf-8") as writer:
        for path in args.runs:
            try:
                metadata, rows = examples(path)
                if metadata["episode_id"] in seen:
                    raise ValueError("Duplicate episode")
                seen.add(metadata["episode_id"])
                for row in rows:
                    writer.write(json.dumps(row, separators=(",", ":")) + "\n")
                manifest["episodes"].append({"source": str(path.resolve()), "episode_id": metadata["episode_id"],
                                             "seed": metadata["seed"], "rows": len(rows),
                                             "deck_hashes": [deck["staged_sha256"] for deck in metadata["decks"]]})
                manifest["rows"] += len(rows)
            except (ValueError, KeyError, OSError) as ex:
                manifest["rejected"].append({"source": str(path), "reason": str(ex)})
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"accepted": len(manifest["episodes"]), "rows": manifest["rows"], "rejected": manifest["rejected"]}, indent=2))
    raise SystemExit(0 if manifest["rows"] else 1)


if __name__ == "__main__":
    main()
