# rewards/base.py
from __future__ import annotations
from typing import Dict, Any, Protocol, Optional, List
from dataclasses import dataclass, field
import numpy as np


# ============================================================
#  1. Reward 接口定义
# ============================================================

class IReward(Protocol):
    """统一接口: 每一步环境反馈后计算 reward"""
    def compute(self, info: Dict[str, Any]) -> float:
        ...


# ============================================================
#  2. 奖励项权重定义（Instance Voltage 优化）
# ============================================================

@dataclass
class RewardWeights:
    """
    基于 inst_voltage 前后对比的多目标加权系数
    
    维度说明:
      - w_violation: 违例数量减少 (优先级最高)
      - w_min_voltage: 最小电压增加 (重点关注)
      - w_mean_voltage: 平均电压增加 (次要目标)
      - step_penalty: 每步固定惩罚 (鼓励少步)
      - invalid_action_penalty: 非法动作惩罚
    """
    w_violation: float = 2.0           # 违例减少：优先级最高
    w_min_voltage: float = 1.5         # 最小电压增加：重点关注
    w_mean_voltage: float = 0.5        # 平均电压增加：次要
    step_penalty: float = 0.0          # 每步固定惩罚
    invalid_action_penalty: float = -1.0  # 非法动作惩罚


# ============================================================
#  3. 电压及违例指标（前后对比的中间数据结构）
# ============================================================

@dataclass
class VoltageMetrics:
    """
    某一时刻的电压及违例统计指标
    """
    inst_voltage_list: List[float] = field(default_factory=list)  # 所有 instance 的电压
    min_voltage: float = 0.0                                       # 最小电压
    mean_voltage: float = 0.0                                      # 平均电压
    max_voltage: float = 0.0                                       # 最大电压
    violation_count: int = 0                                       # 违例数量
    
    @staticmethod
    def from_info(info: Dict[str, Any]) -> 'VoltageMetrics':
        """从环境返回的 info 字典构造电压指标"""
        volt_list = info.get("inst_voltage", [])
        if volt_list is None:
            volt_list = []
        volt_list = [float(v) for v in volt_list]
        
        # 违例可以是列表（违例的 instance 列表）或直接是数字（违例数量）
        violation = info.get("violations", info.get("violation_list", []))
        if isinstance(violation, (list, tuple)):
            violation_count = len(violation)
        else:
            violation_count = int(violation) if violation else int(info.get("violation_count", 0))
        
        metrics = VoltageMetrics()
        metrics.inst_voltage_list = volt_list
        metrics.violation_count = max(0, violation_count)
        
        if volt_list:
            metrics.min_voltage = float(np.min(volt_list))
            metrics.mean_voltage = float(np.mean(volt_list))
            metrics.max_voltage = float(np.max(volt_list))
        
        return metrics


# ============================================================
#  4. Instance Voltage 优化奖励函数（核心）
# ============================================================

class VoltageOptimizationReward(IReward):
    """
    基于 inst_voltage 前后对比的奖励函数（核心设计）
    
    核心逻辑：
      1. 初始化阶段：在 episode 开始或第一步时，通过 set_baseline() 或自动 detect，
         记录 baseline（初始电压报表）。
      
      2. 每步计算：对比当前 metrics 与 baseline，计算三个维度的改善：
         - Δ violation = baseline_violation - current_violation
           （减少为正，增加为负；权重最高，优先级最高）
         
         - Δ min_voltage = current_min_voltage - baseline_min_voltage
           （增加为正，减少为负；重点关注）
         
         - Δ mean_voltage = current_mean_voltage - baseline_mean_voltage
           （增加为正，减少为负；次要目标）
      
      3. 加权求和：
         reward = w_violation * scale_violation * Δviolation
                + w_min_voltage * scale_voltage * Δmin_voltage
                + w_mean_voltage * scale_voltage * Δmean_voltage
                - step_penalty
      
      4. 优先级体现：当违例减少较多时，即使最小电压有所下降也可接受
         （通过 w_violation 权重最大来实现）
      
      5. 非法动作：直接给 invalid_action_penalty，不进行前后对比
    
    使用方式：
      # 方式 1: 自动 detect（推荐）
      reward_fn = VoltageOptimizationReward(weights=RewardWeights())
      reward = reward_fn.compute(info)  # 第一次自动设置 baseline，后续进行对比
      
      # 方式 2: 显式 reset（用于多 episode）
      for episode in episodes:
          reward_fn.reset()  # 清空 baseline
          for step in steps:
              reward = reward_fn.compute(info)
    """
    
    def __init__(
        self,
        weights: RewardWeights | None = None,
        violation_scale: float = 10.0,     # 违例减少的奖励尺度（单位）
        voltage_scale: float = 1.0,        # 电压变化的奖励尺度（单位）
        clip_min: float | None = -5.0,     # reward 下限
        clip_max: float | None = 5.0,      # reward 上限
    ) -> None:
        self.weights = weights or RewardWeights()
        self.violation_scale = float(violation_scale)
        self.voltage_scale = float(voltage_scale)
        self.clip_min = clip_min
        self.clip_max = clip_max
        
        # 用于存储 baseline （episode 开始时设置）
        self.baseline_metrics: Optional[VoltageMetrics] = None
    
    def reset(self) -> None:
        """在 episode 开始时调用，清空 baseline"""
        self.baseline_metrics = None
    
    def set_baseline(self, info: Dict[str, Any]) -> None:
        """显式设置 baseline（一般在 reset 后的第一个 step 自动调用）"""
        self.baseline_metrics = VoltageMetrics.from_info(info)
    
    def compute(self, info: Dict[str, Any]) -> float:
        """
        计算奖励值。
        
        逻辑：
          1. 检查动作合法性。若非法，直接返回 invalid_action_penalty
          2. 若未设置 baseline，自动设置并返回 0.0
          3. 否则对比 baseline，计算三维度改善，加权求和
          4. 裁剪后返回
        """
        w = self.weights
        
        # 1. 检查动作合法性
        if not info.get("valid_action", True):
            penalty = float(w.invalid_action_penalty)
            if self.clip_min is not None or self.clip_max is not None:
                penalty = float(np.clip(
                    penalty,
                    self.clip_min if self.clip_min is not None else penalty,
                    self.clip_max if self.clip_max is not None else penalty,
                ))
            return penalty
        
        # 2. 解析当前 metrics
        current_metrics = VoltageMetrics.from_info(info)
        
        # 3. 若未设置 baseline，自动设置并返回 0
        if self.baseline_metrics is None:
            self.baseline_metrics = current_metrics
            return 0.0
        
        # 4. 计算前后变化（三个维度）
        delta_violation = self.baseline_metrics.violation_count - current_metrics.violation_count
        delta_min_voltage = current_metrics.min_voltage - self.baseline_metrics.min_voltage
        delta_mean_voltage = current_metrics.mean_voltage - self.baseline_metrics.mean_voltage
        
        # 5. 分别计算各维度的奖励贡献
        r_violation = delta_violation * self.violation_scale
        r_min_voltage = delta_min_voltage * self.voltage_scale
        r_mean_voltage = delta_mean_voltage * self.voltage_scale
        
        # 6. 加权求和
        total_reward = (
            w.w_violation * r_violation +
            w.w_min_voltage * r_min_voltage +
            w.w_mean_voltage * r_mean_voltage
        )
        
        # 7. 每步固定惩罚（鼓励少步）
        total_reward -= w.step_penalty
        
        # 8. 裁剪 reward
        if self.clip_min is not None or self.clip_max is not None:
            total_reward = float(np.clip(
                total_reward,
                self.clip_min if self.clip_min is not None else total_reward,
                self.clip_max if self.clip_max is not None else total_reward,
            ))
        
        return float(total_reward)


# ============================================================
#  5. 组合奖励（多目标加权，目前由 Voltage 主导）
# ============================================================

class CompositeReward(IReward):
    """
    用于未来扩展多指标奖励。当前由 VoltageOptimizationReward 主导。
    """
    
    def __init__(
        self,
        weights: RewardWeights | None = None,
        violation_scale: float = 10.0,
        voltage_scale: float = 1.0,
        clip_min: float | None = -5.0,
        clip_max: float | None = 5.0,
    ) -> None:
        self.weights = weights or RewardWeights()
        self.voltage_reward = VoltageOptimizationReward(
            weights=self.weights,
            violation_scale=violation_scale,
            voltage_scale=voltage_scale,
            clip_min=clip_min,
            clip_max=clip_max,
        )
    
    def reset(self) -> None:
        """重置内部 baseline（新 episode 时调用）"""
        self.voltage_reward.reset()
    
    def compute(self, info: Dict[str, Any]) -> float:
        """计算总奖励"""
        r_voltage = self.voltage_reward.compute(info)
        total = r_voltage  # 未来可加其他指标
        return total


# ============================================================
#  6. 工厂函数（便捷创建）
# ============================================================

def make_reward(cfg: Dict[str, Any] | None = None) -> CompositeReward:
    """
    从配置字典构造奖励函数。
    
    配置示例:
        reward_cfg = {
            "weights": {
                "w_violation": 2.0,        # 违例减少权重（最高优先级）
                "w_min_voltage": 1.5,      # 最小电压增加权重
                "w_mean_voltage": 0.5,     # 平均电压增加权重
                "step_penalty": 0.01,      # 每步惩罚（可选）
                "invalid_action_penalty": -1.0,  # 非法动作惩罚
            },
            "violation_scale": 10.0,       # 违例减少 1 个对应的奖励
            "voltage_scale": 1.0,          # 电压增加 0.01V 对应的奖励
            "clip_min": -5.0,              # 奖励下限
            "clip_max": 5.0,               # 奖励上限
        }
        reward_fn = make_reward(reward_cfg)
    """
    cfg = cfg or {}
    
    weights_dict = cfg.get("weights", {})
    weights = RewardWeights(**weights_dict) if weights_dict else RewardWeights()
    
    violation_scale = float(cfg.get("violation_scale", 10.0))
    voltage_scale = float(cfg.get("voltage_scale", 1.0))
    clip_min = cfg.get("clip_min", -5.0)
    clip_max = cfg.get("clip_max", 5.0)
    
    return CompositeReward(
        weights=weights,
        violation_scale=violation_scale,
        voltage_scale=voltage_scale,
        clip_min=clip_min,
        clip_max=clip_max,
    )
