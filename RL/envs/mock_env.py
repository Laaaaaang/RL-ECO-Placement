# envs/mock_env.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
import numpy as np
from .eco_env import decode_xy_from_bins


class MockEnv:
    """
    可训练伪环境（带 IR-drop 模拟）：
    - 观测 obs 恒定（contextual bandit）
    - 动作 MultiDiscrete: [cell_idx, x_bin, y_bin]
    - 每一步返回一个假的 IR-drop 结果，用于奖励函数
    - 奖励: 低 IR-drop 高奖励；过高 IR-drop 负奖励
    """

    def __init__(
        self,
        obs_vec: np.ndarray,
        meta: Dict[str, Any],
        action_dims: List[int],
        irdrop_target: float = 0.05,   # 目标 IR-drop（越小越好）
        noise_level: float = 0.01,     # 模拟测量噪声
    ) -> None:
        self.obs_vec = obs_vec.astype(np.float32)
        self.meta = meta
        self.top_k = int(meta["top_k"])
        self.taken = int(meta["taken"])
        self.x_range: Tuple[float, float] = tuple(meta["x_range"])
        self.y_range: Tuple[float, float] = tuple(meta["y_range"])
        self.x_bins, self.y_bins = int(action_dims[1]), int(action_dims[2])

        # 芯片中心
        self.xc = (self.x_range[0] + self.x_range[1]) * 0.5
        self.yc = (self.y_range[0] + self.y_range[1]) * 0.5
        self.dx = max(1e-9, self.x_range[1] - self.x_range[0])
        self.dy = max(1e-9, self.y_range[1] - self.y_range[0])

        self.irdrop_target = float(irdrop_target)
        self.noise_level = float(noise_level)
        self.step_count = 0

    # ----------------------------
    # 环境接口
    # ----------------------------
    def reset(self, *, seed: Optional[int] = None) -> Tuple[np.ndarray, Dict[str, Any]]:
        self.step_count = 0
        return self.obs_vec.copy(), {"center": (self.xc, self.yc), "taken": self.taken}

    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        """
        action: [cell_idx, x_bin, y_bin]
        - 产生假 IR-drop 值：距离中心越远，IR-drop 越大
        - 计算 reward: 基于 IR-drop 与目标差异
        """
        a = np.asarray(action, dtype=np.int64).tolist()
        cell_idx, x_bin, y_bin = int(a[0]), int(a[1]), int(a[2])

        info: Dict[str, Any] = {}

        # 非法 cell（padding 区）
        if cell_idx >= self.taken:
            reward = -2.0
            fake_irdrop = 0.1  # 随便一个高 IRdrop 值
            info.update({
                "cell_valid": False,
                "reason": "padded_row",
                "irdrop": fake_irdrop,
            })
        else:
            # 解码目标坐标
            tx, ty = decode_xy_from_bins(
                x_bin, y_bin, self.x_bins, self.y_bins,
                self.x_range, self.y_range
            )
            # 模拟 IR-drop：离中心越远 IR-drop 越高 + 噪声
            nx = (tx - self.xc) / self.dx
            ny = (ty - self.yc) / self.dy
            dist = np.sqrt(nx**2 + ny**2)
            base_drop = 0.02 + 0.08 * dist  # 基础 0.02V 起，离中心线性上升
            fake_irdrop = float(base_drop + np.random.uniform(-self.noise_level, self.noise_level))

            # 奖励函数：低于目标→正，高于目标→负，线性惩罚
            # 例如：reward = 1 - (IRdrop / target)
            ratio = fake_irdrop / self.irdrop_target
            reward = 1.0 - ratio
            reward = float(np.clip(reward, -2.0, 1.0))  # 裁剪防爆

            info.update({
                "cell_valid": True,
                "decoded": {"target_x": tx, "target_y": ty, "dist": float(dist)},
                "irdrop": fake_irdrop,
                "irdrop_target": self.irdrop_target,
            })

        obs_next = self.obs_vec.copy()  # 恒定观测
        terminated = False
        truncated = False
        self.step_count += 1
        return obs_next, reward, terminated, truncated, info
