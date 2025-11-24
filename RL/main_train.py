# main_train.py
from __future__ import annotations
import os
import numpy as np
import torch
import torch.optim as optim

from utils.config import load_cfg
from utils.logger import TBLogger
from envs.prepare_data import run as prepare_data_run
from envs.mock_env import MockEnv
from nets.actor_critic import MultiDiscreteActor, ValueHead
from algo.storage import RolloutBuffer
from algo.ppo import PPOTrainer

def main():
    # --- 配置与设备 ---
    cfg = load_cfg("configs/ppo_eco.yaml")
    device = torch.device(getattr(cfg, "device", "cpu"))

    # 安全取配置项
    act_cfg = getattr(cfg, "action_space", None)
    if act_cfg is None:
        # 默认动作空间
        class Dummy: pass
        act_cfg = Dummy()
        act_cfg.top_k = 128
        act_cfg.x_bins = 64
        act_cfg.y_bins = 64

    run_dir = getattr(cfg, "run_dir", "runs/eco_ppo_mock")
    logger = TBLogger(run_dir)

    # --- 数据准备：确保 features/meta 就绪 ---
    env_dir = os.path.join(os.path.dirname(__file__), "envs")
    raw_csv = os.path.join(env_dir, "raw_data.csv")
    if not os.path.exists(raw_csv):
        raise FileNotFoundError(f"raw_data.csv not found at: {raw_csv}")

    raw_csv, cell_csv, feat_npz, meta = prepare_data_run(
        raw_path=raw_csv, out_dir=env_dir, top_k=act_cfg.top_k, sort_by=None
    )
    npz = np.load(feat_npz)
    obs_vec = npz["obs"]  # shape: (obs_dim,)

    # --- 观测/动作维度 ---
    F = int(meta["feature_dim"])
    top_k = int(meta["top_k"])
    obs_dim = top_k * (F + 1)  # +1 for mask
    action_dims = [top_k, int(act_cfg.x_bins), int(act_cfg.y_bins)]  # [cell_idx, x_bin, y_bin]
    act_heads = len(action_dims)

    # --- 构建网络 ---
    actor = MultiDiscreteActor(in_dim=obs_dim, action_dims=action_dims, hid=getattr(cfg.model, "hidden", 128)).to(device)
    critic = ValueHead(in_dim=obs_dim, hid=getattr(cfg.model, "hidden", 128)).to(device)
    optimizer = optim.Adam(
        list(actor.parameters()) + list(critic.parameters()),
        lr=getattr(cfg.opt, "lr", 3e-4), weight_decay=getattr(cfg.opt, "wd", 0.0)
    )

    # --- 假环境（contextual bandit） ---
    mock_env = MockEnv(obs_vec=obs_vec, meta=meta, action_dims=action_dims)
    obs_np, _ = mock_env.reset()
    # 统一批大小（并行环境数）
    num_envs = 1
    obs = torch.from_numpy(obs_np).to(device).float().unsqueeze(0)  # [1, obs_dim]

    # --- 采样 & 训练循环（闭环） ---
    steps_per_rollout = int(getattr(cfg, "steps_per_rollout", 64))
    updates = int(getattr(cfg, "updates", 10))
    ppo_cfg = getattr(cfg, "ppo", None)
    # 供 PPOTrainer 直接拿（扁平 SimpleNamespace）
    class PPOCfg: pass
    pc = PPOCfg()
    pc.gamma = getattr(ppo_cfg, "gamma", 0.99)
    pc.lam = getattr(ppo_cfg, "lam", 0.95)
    pc.clip_ratio = getattr(ppo_cfg, "clip_ratio", 0.2)
    pc.vf_coef = getattr(ppo_cfg, "vf_coef", 0.5)
    pc.ent_coef = getattr(ppo_cfg, "ent_coef", 0.01)
    pc.update_epochs = getattr(ppo_cfg, "update_epochs", 2)
    pc.batch_size = getattr(ppo_cfg, "batch_size", 1024)
    pc.max_grad_norm = getattr(ppo_cfg, "max_grad_norm", 1.0)

    trainer = PPOTrainer(actor, critic, optimizer, pc, logger)
    buffer = RolloutBuffer(
        num_steps=steps_per_rollout, num_envs=num_envs, obs_dim=obs_dim, act_dim=act_heads, device=device
    )

    global_step = 0
    for up in range(updates):
        buffer.ptr = 0
        # ========== 采样 ==========
        for t in range(steps_per_rollout):
            with torch.no_grad():
                action, logp, value = trainer.act(obs)  # action:[1, H], logp:[1], value:[1]

            # 与 mock 环境交互
            act_np = action.squeeze(0).cpu().numpy()  # [H]
            obs_next_np, reward_f, done_b, trunc_b, info = mock_env.step(act_np)

            # 写入 buffer
            reward = torch.tensor([reward_f], dtype=torch.float32, device=device)   # [1]
            done = torch.tensor([False], dtype=torch.bool, device=device)           # [1]  # bandit 不终止
            buffer.add(
                obs=obs, action=action, reward=reward, done=done, value=value, logp=logp
            )

            # 准备下一个 obs（恒定）
            obs = torch.from_numpy(obs_next_np).to(device).float().unsqueeze(0)
            global_step += num_envs

        # rollout 末尾 bootstrap
        with torch.no_grad():
            last_value = critic(obs).squeeze(-1)  # [1]

        # ========== 更新 ==========
        stats = trainer.update(buffer, last_value)
        logger.log({"update": up, **stats, "global_step": global_step})

        # 观察学习是否进行：打印近几次奖励均值（buffer 中 rewards 的均值只是采样分布的近似）
        mean_r = float(buffer.rewards.mean().detach().cpu())
        print(f"[update {up}] mean_reward={mean_r:.4f}, stats={stats}")

    print("Done. Closed-loop mock training finished.")

if __name__ == "__main__":
    main()
