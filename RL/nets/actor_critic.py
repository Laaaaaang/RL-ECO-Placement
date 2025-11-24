from __future__ import annotations
from typing import List, Tuple
import torch
import torch.nn as nn
from torch.distributions import Categorical

class MLPEncoder(nn.Module):
    def __init__(self, in_dim: int, hid: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, hid), nn.ReLU(),
            nn.Linear(hid, hid), nn.ReLU(),
        )
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)

class JointMultiCategorical:
    def __init__(self, dists: List[Categorical]):
        self.dists = dists
    def sample(self) -> torch.Tensor:
        return torch.stack([d.sample() for d in self.dists], dim=-1)
    def log_prob(self, actions: torch.Tensor) -> torch.Tensor:
        parts = [d.log_prob(a) for d, a in zip(self.dists, actions.unbind(-1))]
        return torch.stack(parts, dim=-1).sum(-1)
    def entropy(self) -> torch.Tensor:
        return torch.stack([d.entropy() for d in self.dists], dim=-1).sum(-1)

class MultiDiscreteActor(nn.Module):
    def __init__(self, in_dim: int, action_dims: List[int], hid: int = 128):
        super().__init__()
        self.enc = MLPEncoder(in_dim, hid)
        self.heads = nn.ModuleList([nn.Linear(hid, d) for d in action_dims])
    def forward(self, obs: torch.Tensor):
        h = self.enc(obs)
        dists = [Categorical(logits=head(h)) for head in self.heads]
        return JointMultiCategorical(dists)
    def evaluate(self, obs: torch.Tensor, actions: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        dist = self.forward(obs)
        logp = dist.log_prob(actions)
        ent = dist.entropy()
        return logp, ent

class ValueHead(nn.Module):
    def __init__(self, in_dim: int, hid: int = 128):
        super().__init__()
        self.enc = MLPEncoder(in_dim, hid)
        self.v = nn.Linear(hid, 1)
    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        return self.v(self.enc(obs))
