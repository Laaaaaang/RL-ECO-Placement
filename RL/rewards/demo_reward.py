#!/usr/bin/env python
"""
示例：演示新的 VoltageOptimizationReward 的工作方式
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from base import make_reward, VoltageOptimizationReward, RewardWeights
import json


def example_1_good_improvement():
    """示例 1：优秀的改善（违例减少 + 电压增加）"""
    print("\n" + "="*70)
    print("示例 1：优秀的改善（违例减少 + 电压增加）")
    print("="*70)
    
    # 初始状态（baseline）
    baseline_info = {
        "inst_voltage": [0.70, 0.75, 0.80, 0.85, 0.90],
        "violations": [2, 4],  # 2 个违例的 instance 索引
        "valid_action": True,
    }
    
    # 动作后的状态
    current_info = {
        "inst_voltage": [0.75, 0.78, 0.82, 0.87, 0.92],
        "violations": [],  # 无违例
        "valid_action": True,
    }
    
    # 创建奖励函数
    reward_fn = VoltageOptimizationReward(
        violation_scale=10.0,
        voltage_scale=1.0,
    )
    
    # 第一次调用自动设置 baseline
    r1 = reward_fn.compute(baseline_info)
    print(f"Step 1 (baseline): reward = {r1:.4f}")
    
    # 第二次调用进行对比
    r2 = reward_fn.compute(current_info)
    print(f"Step 2 (improved): reward = {r2:.4f}")
    
    print("\n分析：")
    print(f"  - 违例数：2 → 0 （减少 2 个）")
    print(f"  - 最小电压：0.70V → 0.75V （增加 0.05V）")
    print(f"  - 平均电压：0.80V → 0.828V （增加 0.028V）")
    print(f"  - 预期奖励 ≈ 2.0*10*2 + 1.5*1*0.05 + 0.5*1*0.028 = 40.089")
    

def example_2_violation_dominates():
    """示例 2：违例减少但电压略降（验证优先级）"""
    print("\n" + "="*70)
    print("示例 2：违例减少但电压略降（验证优先级）")
    print("="*70)
    
    baseline_info = {
        "inst_voltage": [0.80, 0.85, 0.90, 0.88],
        "violations": [0, 1, 3],  # 3 个违例
        "valid_action": True,
    }
    
    current_info = {
        "inst_voltage": [0.78, 0.87, 0.92, 0.90],  # 最小值略降
        "violations": [],  # 但违例全消除
        "valid_action": True,
    }
    
    reward_fn = VoltageOptimizationReward(
        violation_scale=10.0,
        voltage_scale=1.0,
    )
    
    r1 = reward_fn.compute(baseline_info)
    print(f"Step 1 (baseline): reward = {r1:.4f}")
    
    r2 = reward_fn.compute(current_info)
    print(f"Step 2 (violation reduced): reward = {r2:.4f}")
    
    print("\n分析：")
    print(f"  - 违例数：3 → 0 （减少 3 个）")
    print(f"  - 最小电压：0.80V → 0.78V （减少 0.02V）")
    print(f"  - 平均电压：0.8575V → 0.8675V （增加 0.01V）")
    print(f"  - 预期奖励 ≈ 2.0*10*3 + 1.5*1*(-0.02) + 0.5*1*0.01 = 59.985")
    print(f"  - 即使最小电压下降，奖励仍然很高！验证了优先级")


def example_3_invalid_action():
    """示例 3：非法动作（直接惩罚）"""
    print("\n" + "="*70)
    print("示例 3：非法动作（直接惩罚）")
    print("="*70)
    
    info_invalid = {
        "inst_voltage": [0.70, 0.75, 0.80],
        "violations": [],
        "valid_action": False,  # 非法动作
    }
    
    reward_fn = VoltageOptimizationReward(
        violation_scale=10.0,
        voltage_scale=1.0,
    )
    
    reward = reward_fn.compute(info_invalid)
    print(f"Reward for invalid action: {reward:.4f}")
    print(f"（直接返回 invalid_action_penalty = -1.0，无需对比）")


def example_4_custom_weights():
    """示例 4：自定义权重（更看重电压）"""
    print("\n" + "="*70)
    print("示例 4：自定义权重（更看重电压）")
    print("="*70)
    
    # 自定义权重：减少对违例的权重，增加对电压的权重
    weights = RewardWeights(
        w_violation=1.0,       # 从 2.0 降到 1.0
        w_min_voltage=2.0,     # 从 1.5 升到 2.0
        w_mean_voltage=1.0,    # 从 0.5 升到 1.0
    )
    
    baseline_info = {
        "inst_voltage": [0.70, 0.75, 0.80],
        "violations": [0],  # 1 个违例
        "valid_action": True,
    }
    
    current_info = {
        "inst_voltage": [0.72, 0.77, 0.82],
        "violations": [0],  # 仍有 1 个违例
        "valid_action": True,
    }
    
    reward_fn = VoltageOptimizationReward(
        weights=weights,
        violation_scale=10.0,
        voltage_scale=1.0,
    )
    
    r1 = reward_fn.compute(baseline_info)
    print(f"Step 1 (baseline): reward = {r1:.4f}")
    
    r2 = reward_fn.compute(current_info)
    print(f"Step 2 (voltage improved, violation unchanged): reward = {r2:.4f}")
    
    print("\n分析：")
    print(f"  - 违例数：1 → 1 （无变化）")
    print(f"  - 最小电压：0.70V → 0.72V （增加 0.02V）")
    print(f"  - 平均电压：0.75V → 0.7633V （增加 0.0133V）")
    print(f"  - 使用新权重，更看重电压的增加")
    print(f"  - 预期奖励 ≈ 1.0*10*0 + 2.0*1*0.02 + 1.0*1*0.0133 = 0.0533")


def example_5_factory_function():
    """示例 5：使用工厂函数和配置字典"""
    print("\n" + "="*70)
    print("示例 5：使用工厂函数和配置字典")
    print("="*70)
    
    config = {
        "weights": {
            "w_violation": 2.0,
            "w_min_voltage": 1.5,
            "w_mean_voltage": 0.5,
            "step_penalty": 0.05,
        },
        "violation_scale": 10.0,
        "voltage_scale": 1.0,
        "clip_min": -5.0,
        "clip_max": 5.0,
    }
    
    print("Configuration:")
    print(json.dumps(config, indent=2))
    
    reward_fn = make_reward(config)
    
    baseline_info = {
        "inst_voltage": [0.70, 0.75, 0.80],
        "violations": [1],
        "valid_action": True,
    }
    
    current_info = {
        "inst_voltage": [0.72, 0.77, 0.82],
        "violations": [],
        "valid_action": True,
    }
    
    r1 = reward_fn.compute(baseline_info)
    print(f"\nStep 1 (baseline): reward = {r1:.4f}")
    
    r2 = reward_fn.compute(current_info)
    print(f"Step 2 (improved): reward = {r2:.4f}")
    
    print(f"\n预期奖励 ≈ 2.0*10*1 + 1.5*1*0.02 + 0.5*1*0.0133 - 0.05 = {20 + 0.03 + 0.0067 - 0.05:.4f}")


if __name__ == "__main__":
    print("\n" + "#"*70)
    print("# VoltageOptimizationReward 演示脚本")
    print("#"*70)
    
    example_1_good_improvement()
    example_2_violation_dominates()
    example_3_invalid_action()
    example_4_custom_weights()
    example_5_factory_function()
    
    print("\n" + "#"*70)
    print("# 演示完成")
    print("#"*70 + "\n")
