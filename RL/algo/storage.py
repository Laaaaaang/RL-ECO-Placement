from __future__ import annotations
from typing import Dict, Iterator
import torch

class RolloutBuffer:
    def __init__(self, num_steps, num_envs, obs_dim, act_dim, device):
        self.obs = torch.zeros(num_steps, num_envs, obs_dim, device=device)
        self.actions = torch.zeros(num_steps, num_envs, act_dim, device=device, dtype=torch.long)
        self.rewards = torch.zeros(num_steps, num_envs, device=device)
        self.dones = torch.zeros(num_steps, num_envs, device=device, dtype=torch.bool)
        self.values = torch.zeros(num_steps, num_envs, device=device)
        self.logps = torch.zeros(num_steps, num_envs, device=device)
        self.ptr = 0; self.device = device
        self.num_steps = num_steps; self.num_envs = num_envs

    def add(self, obs, action, reward, done, value, logp):
        self.obs[self.ptr] = obs; self.actions[self.ptr] = action
        self.rewards[self.ptr] = reward; self.dones[self.ptr] = done
        self.values[self.ptr] = value; self.logps[self.ptr] = logp
        self.ptr += 1

    def flatten(self) -> Dict[str, torch.Tensor]:
        T, N = self.rewards.shape
        def _f(x): return x.reshape(T * N, *x.shape[2:]) if x.dim() > 2 else x.reshape(T * N)
        return {"obs": _f(self.obs), "actions": _f(self.actions),
                "rewards": _f(self.rewards), "dones": _f(self.dones),
                "values": _f(self.values), "logps": _f(self.logps)}

    def iter_minibatches(self, flat: Dict[str, torch.Tensor], adv: torch.Tensor, ret: torch.Tensor, batch_size: int) -> Iterator[Dict[str, torch.Tensor]]:
        X = {**flat, "adv": adv.reshape(-1), "ret": ret.reshape(-1)}
        n = X["obs"].shape[0]; idx = torch.randperm(n, device=self.device)
        for s in range(0, n, batch_size):
            j = idx[s:s+batch_size]
            yield {k: v[j] for k, v in X.items()}
