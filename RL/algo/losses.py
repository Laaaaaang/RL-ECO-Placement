from __future__ import annotations
from typing import Dict, Tuple
import torch

def ppo_loss(policy, value_head, batch: Dict[str, torch.Tensor], clip_ratio: float, vf_coef: float, ent_coef: float) -> Tuple[torch.Tensor, Dict[str, float]]:
    obs = batch["obs"]; actions = batch["actions"]
    old_logp = batch["logps"]; advantages = batch["adv"]; returns = batch["ret"]
    dist = policy(obs)
    logp = dist.log_prob(actions)
    ratio = torch.exp(logp - old_logp)
    clipped = torch.clamp(ratio, 1.0 - clip_ratio, 1.0 + clip_ratio) * advantages
    pg_loss = -(torch.min(ratio * advantages, clipped)).mean()
    values = value_head(obs).squeeze(-1)
    v_loss = torch.mean((values - returns) ** 2)
    ent = dist.entropy().mean()
    loss = pg_loss + vf_coef * v_loss - ent_coef * ent
    return loss, {"pg": float(pg_loss.detach()), "v": float(v_loss.detach()), "ent": float(ent.detach())}
