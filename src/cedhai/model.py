"""Small masked curriculum policy and outcome model; not a full Magic policy."""

from dataclasses import asdict
from pathlib import Path

import torch
from torch import nn

from .engine import Observation
from .learning_data import ACTION_SIZE, MAX_ACTIONS, STATE_SIZE, encode_action, encode_state


class PolicyValueModel(nn.Module):
    def __init__(self, hidden_size=64):
        super().__init__()
        self.hidden_size = hidden_size
        self.state = nn.Sequential(nn.Linear(STATE_SIZE, hidden_size), nn.ReLU())
        self.policy = nn.Sequential(nn.Linear(hidden_size + ACTION_SIZE, hidden_size),
                                    nn.ReLU(), nn.Linear(hidden_size, 1))
        self.value = nn.Linear(hidden_size, 1)

    def forward(self, state, actions, mask):
        if mask.ndim != 2 or mask.dtype != torch.bool or not mask.any(dim=1).all():
            raise ValueError("Each observation needs at least one legal action")
        encoded = self.state(state)
        context = encoded.unsqueeze(1).expand(-1, actions.shape[1], -1)
        logits = self.policy(torch.cat((context, actions), dim=-1)).squeeze(-1)
        return logits.masked_fill(~mask, float("-inf")), self.value(encoded).squeeze(-1)


def load_checkpoint(path: Path):
    # Restricted loading avoids arbitrary pickle execution for model weights.
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    if checkpoint.get("schema_version") != 1 or checkpoint.get("features") != [STATE_SIZE, ACTION_SIZE, MAX_ACTIONS]:
        raise ValueError("Incompatible curriculum checkpoint")
    model = PolicyValueModel(checkpoint["config"]["hidden_size"])
    model.load_state_dict(checkpoint["model"])
    model.eval()
    return model, checkpoint


class ModelAgent:
    def __init__(self, checkpoint: Path):
        self.model, self.checkpoint = load_checkpoint(checkpoint)

    def choose_action(self, observation: Observation):
        actions = observation.legal_actions
        if not 1 <= len(actions) <= MAX_ACTIONS:
            raise ValueError("Unsupported action count")
        state = encode_state(asdict(observation), observation.decision_type)
        vectors = [encode_action(asdict(action), observation.seat) for action in actions]
        vectors += [[0.0] * ACTION_SIZE for _ in range(MAX_ACTIONS - len(actions))]
        mask = [True] * len(actions) + [False] * (MAX_ACTIONS - len(actions))
        with torch.inference_mode():
            logits, _ = self.model(torch.tensor([state]), torch.tensor([vectors]), torch.tensor([mask]))
        return actions[int(logits.argmax(dim=1).item())]
