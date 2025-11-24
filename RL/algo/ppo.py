from __future__ import annotations
from typing import Dict, Any
import torch
from .advantages import compute_gae
from .losses import ppo_loss
from .storage import RolloutBuffer

class PPOTrainer:
    def __init__(self, actor, critic, optimizer, cfg, logger) -> None:
        self.actor = actor; self.critic = critic; self.optimizer = optimizer
        self.cfg = cfg; self.logger = logger

    @torch.no_grad()
    def act(self, obs: torch.Tensor):
        dist = self.actor(obs)
        action = dist.sample()
        logp = dist.log_prob(action)
        value = self.critic(obs).squeeze(-1)
        return action, logp, value

    def update(self, buffer: RolloutBuffer, last_value: torch.Tensor) -> Dict[str, Any]:
        gae = compute_gae(buffer.rewards, buffer.values, buffer.dones, last_value, self.cfg.gamma, self.cfg.lam)
        flat = buffer.flatten()
        stats = {}
        for epoch in range(getattr(self.cfg, "update_epochs", 1)):
            for batch in buffer.iter_minibatches(flat, gae["adv"], gae["ret"], getattr(self.cfg, "batch_size", 1024)):
                loss, m = ppo_loss(self.actor, self.critic, batch,
                                   getattr(self.cfg, "clip_ratio", 0.2),
                                   getattr(self.cfg, "vf_coef", 0.5),
                                   getattr(self.cfg, "ent_coef", 0.0))
                self.optimizer.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    list(self.actor.parameters()) + list(self.critic.parameters()),
                    getattr(self.cfg, "max_grad_norm", 1.0)
                )
                self.optimizer.step()
                stats = m
        with torch.no_grad():
            stats.update({
                "adv_mean": float(gae["adv"].mean()),
                "ret_mean": float(gae["ret"].mean()),
                "delta_mean": float(gae["delta"].mean()),
                "q_mean": float(gae["q"].mean()),
            })
        return stats
