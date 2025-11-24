from __future__ import annotations
import torch

@torch.no_grad()
def compute_gae(rewards, values, dones, last_value, gamma, lam):
    T, N = rewards.shape
    device = rewards.device
    adv = torch.zeros(T, N, device=device)
    delta_t = torch.zeros_like(rewards)
    gae = torch.zeros(N, device=device)
    for t in reversed(range(T)):
        next_val = last_value if t == T - 1 else values[t + 1]
        nonterminal = (~dones[t]).float()
        delta = rewards[t] + gamma * next_val * nonterminal - values[t]
        delta_t[t] = delta
        gae = delta + gamma * lam * nonterminal * gae
        adv[t] = gae
    ret = adv + values
    q = ret.clone()
    adv = (adv - adv.mean()) / (adv.std() + 1e-8)
    return { "delta": delta_t, "adv": adv, "ret": ret, "q": q }
