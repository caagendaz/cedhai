from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

from cedhai.decision_bridge import DecisionSession
from cedhai.engine import Action
from cedhai.evaluate import seating_plan, summarize
from cedhai.learning_data import ACTION_SIZE, MAX_ACTIONS, STATE_SIZE, encode_action, encode_state, examples, load_episode


def observation(seat=0):
    return {"game_id": "xmage-7", "step": 0, "seat": seat,
            "public_state": {"turn": 1, "active_seat": seat,
                "players": [{"seat": i, "life": 40, "hand_count": 0, "library_count": 99,
                             "in_game": True} for i in range(4)],
                "battlefield": [], "commanders": [], "stack": [], "combat": []},
            "private_state": {"hand": []},
            "legal_actions": [{"id": "pass", "label": "Pass"},
                              {"id": "land:0", "label": "Play Forest",
                               "features": {"colors": [False, False, False, False, True]}}]}


def episode():
    decisions = []
    for step, seat in enumerate((0, 1, 0)):
        data = observation(seat)
        data["step"] = step
        request_id = f"xmage-7:{step}"
        decisions.extend([
            {"event": "decision", "schema_version": 2, "request_id": request_id,
             "scope": "priority_basic", "observation": data,
             "response": {"request_id": request_id, "action_id": "pass"}},
            {"event": "applied", "schema_version": 2, "request_id": request_id,
             "action_id": "pass", "seat": seat, "zone": "NONE"},
        ])
    finished = {"event": "finished", "schema_version": 2, "game_id": "xmage-7", "terminal": True,
                "truncated": False, "decisions": 3, "applied_lands": 0, "cast_spells": 0,
                "resolved_spells": 0, "attacks": 0, "blocks": 0, "winners": [0], "rewards": [1.0, 0.0, 0.0, 0.0]}
    return decisions + [finished]


def save_episode(path, events, seed=7):
    metadata = {"success": True, "mode": "basic", "observation_features_version": 1, "seed": seed,
                "seat_policies": ["random"] * 4, "completion": events[-1]}
    (path / "result.json").write_text(json.dumps(metadata))
    (path / "trajectory.jsonl").write_text("\n".join(json.dumps(event) for event in events) + "\n")


class LearningDataTests(unittest.TestCase):
    def test_actor_transitions_padding_and_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            save_episode(path, episode())
            _, rows = examples(path)
            self.assertEqual(len(rows), 3)
            self.assertEqual(len(rows[0]["state"]), STATE_SIZE)
            self.assertEqual(len(rows[0]["actions"]), MAX_ACTIONS)
            self.assertEqual(len(rows[0]["actions"][0]), ACTION_SIZE)
            self.assertEqual(sum(rows[0]["action_mask"]), 2)
            self.assertEqual(rows[0]["next_state"], rows[2]["state"])
            self.assertFalse(rows[0]["terminated"])
            self.assertEqual(rows[0]["reward"], 0.0)
            self.assertEqual(rows[2]["reward"], 1.0)
            self.assertEqual(rows[1]["outcome_target"], 0.0)
            self.assertNotIn("xmage", json.dumps(rows[0]["state"]))
            self.assertEqual(rows[0]["split"], "train")

    def test_truncation_incomplete_application_and_wrong_outcomes_are_rejected(self):
        for problem in ("truncated", "missing_application", "wrong_action", "wrong_reward"):
            with self.subTest(problem=problem), tempfile.TemporaryDirectory() as tmp:
                events = episode()
                if problem == "truncated":
                    events[-1].update(terminal=False, truncated=True)
                elif problem == "missing_application":
                    del events[1]
                elif problem == "wrong_action":
                    events[1]["action_id"] = "land:0"
                else:
                    events[-1]["rewards"] = [0.0] * 4
                save_episode(Path(tmp), events)
                with self.assertRaises(ValueError):
                    load_episode(Path(tmp))

    def test_seed_split_and_color_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            save_episode(Path(tmp), episode(), seed=10)
            _, rows = examples(Path(tmp))
            self.assertEqual({row["split"] for row in rows}, {"validation"})
        obs = observation()
        first = encode_action(obs["legal_actions"][1], 0)
        second = deepcopy(obs["legal_actions"][1])
        second["features"]["colors"] = [False, False, True, False, False]
        self.assertNotEqual(first, encode_action(second, 0))
        self.assertEqual(encode_state(observation(0), "priority_basic"), encode_state(observation(2), "priority_basic"))

    def test_external_agents_select_choices_and_invalid_choices_fail_closed(self):
        class Agent:
            def __init__(self, action):
                self.action = action
            def choose_action(self, obs):
                self.scope = obs.decision_type
                return self.action
        agent = Agent(Action("pass", "Pass"))
        session = DecisionSession(io.StringIO(), 7, agents=(agent,) * 4)
        event = {"schema_version": 2, "event": "decision", "request_id": "xmage-7:0",
                 "scope": "priority_basic", "observation": observation()}
        self.assertEqual(session.handle(event)["action_id"], "pass")
        self.assertEqual(agent.scope, "priority_basic")
        wrong = Agent(Action("cast:999", "Unavailable"))
        with self.assertRaisesRegex(ValueError, "unavailable"):
            DecisionSession(io.StringIO(), 7, agents=(wrong,) * 4).handle(event)


class EvaluationTests(unittest.TestCase):
    def test_each_profile_visits_each_seat_per_seed(self):
        plan = seating_plan([7, 10])
        for seed in (7, 10):
            block = [item for item in plan if item["seed"] == seed]
            for profile in range(4):
                self.assertEqual(sorted(item["seat_to_profile"].index(profile) for item in block), [0, 1, 2, 3])
        with self.assertRaises(ValueError):
            seating_plan([7, 7])

    def test_winners_are_mapped_to_profiles_and_truncation_is_excluded(self):
        game = {"seed": 7, "success": True, "terminal": True, "truncated": False,
                "seat_to_profile": [1, 2, 3, 0], "winners": [3]}
        truncation = {**game, "seed": 8, "truncated": True, "terminal": False, "winners": []}
        summary = summarize([game, truncation], ["random"] * 4)
        self.assertEqual(summary["profiles"][0]["wins"], 1)
        self.assertEqual(summary["profiles"][0]["completed"], 1)
        self.assertEqual(summary["profiles"][0]["truncated"], 1)
        self.assertIsNone(summary["profiles"][0]["seed_block_bootstrap_95"])

    def test_uncertainty_uses_seed_blocks(self):
        games = [{**item, "success": True, "terminal": True, "truncated": False, "winners": [0]}
                 for item in seating_plan([1, 2, 3, 4, 5])]
        summary = summarize(games, ["random"] * 4)
        self.assertEqual(summary["complete_seed_blocks"], 5)
        self.assertEqual(summary["profiles"][0]["seed_block_bootstrap_95"], [0.25, 0.25])
