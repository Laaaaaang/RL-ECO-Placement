# 快速入门指南 - 奖励函数

## 1️⃣ 最简单的使用方式

```python
from rewards import make_reward

# 创建奖励函数（使用默认参数）
reward_fn = make_reward()

# 在训练循环中
for episode in range(num_episodes):
    obs, info = env.reset()
    reward_fn.reset()  # 重置 baseline
    
    for step in range(max_steps):
        action = agent.select_action(obs)
        obs, _, done, truncated, info = env.step(action)
        
        # 直接计算奖励
        reward = reward_fn.compute(info)
        agent.step(obs, reward, done, truncated)
```

## 2️⃣ 环境需要返回什么？

你的环境 `env.step()` 返回的 `info` 字典需要包含：

```python
info = {
    # 必需：所有 instance 的电压列表（浮点数）
    "inst_voltage": [0.70, 0.75, 0.80, 0.85, 0.90],
    
    # 可选：违例信息（以下任选一种）
    "violations": [inst_2, inst_4],  # 方式 1: 违例 instance 的列表
    # 或
    "violation_count": 2,             # 方式 2: 违例数量整数
    
    # 可选：动作是否合法（默认 True）
    "valid_action": True,  # 如果 False，直接返回惩罚 -1.0
}
```

## 3️⃣ 核心奖励公式

```
reward = w_violation * violation_scale * (Δviolation)
       + w_min_voltage * voltage_scale * (Δmin_voltage)
       + w_mean_voltage * voltage_scale * (Δmean_voltage)
       - step_penalty
```

其中：
- `Δviolation = baseline_violation - current_violation`（减少为正）
- `Δmin_voltage = current_min - baseline_min`（增加为正）
- `Δmean_voltage = current_mean - baseline_mean`（增加为正）

## 4️⃣ 默认权重效果

| 指标 | 权重 | Scale | 单位效果 |
|------|------|-------|---------|
| 违例减少 1 个 | 2.0 | 10.0 | **+20 点** |
| 最小电压增加 0.01V | 1.5 | 1.0 | **+0.015 点** |
| 平均电压增加 0.01V | 0.5 | 1.0 | **+0.005 点** |

**结论**：违例减少的权重远高于电压增加，完全符合你的需求！

## 5️⃣ 具体数值例子

### 例子 1：优秀情况

初始：
```
inst_voltage = [0.70, 0.75, 0.80, 0.85, 0.90]
violations = [inst_0, inst_1]  # 2 个违例
```

动作后：
```
inst_voltage = [0.75, 0.78, 0.82, 0.87, 0.92]
violations = []  # 0 个违例
```

计算：
```
Δviolation = 2 - 0 = 2
Δmin_voltage = 0.75 - 0.70 = 0.05
Δmean_voltage = 0.828 - 0.80 = 0.028

reward = 2.0 * 10.0 * 2 + 1.5 * 1.0 * 0.05 + 0.5 * 1.0 * 0.028
       = 40 + 0.075 + 0.014
       = 40.089  ✅ 优秀！
```

### 例子 2：违例减少但电压略降

初始：
```
inst_voltage = [0.80, 0.85, 0.90, 0.88]
violations = [inst_0, inst_1, inst_3]  # 3 个违例
```

动作后：
```
inst_voltage = [0.78, 0.87, 0.92, 0.90]  # 最小值反而降了！
violations = []  # 但违例全消了
```

计算：
```
Δviolation = 3 - 0 = 3
Δmin_voltage = 0.78 - 0.80 = -0.02  # 负数！
Δmean_voltage = 0.8675 - 0.8575 = 0.01

reward = 2.0 * 10.0 * 3 + 1.5 * 1.0 * (-0.02) + 0.5 * 1.0 * 0.01
       = 60 - 0.03 + 0.005
       = 59.975  ✅ 仍然很好！
```

**这就是你要的优先级！**

## 6️⃣ 调整参数

### 如果你想更看重电压：

```python
from rewards import make_reward

config = {
    "weights": {
        "w_violation": 1.0,        # 从 2.0 降低
        "w_min_voltage": 2.0,      # 从 1.5 提升
        "w_mean_voltage": 1.0,     # 从 0.5 提升
    },
    "violation_scale": 5.0,        # 从 10.0 降低
    "voltage_scale": 2.0,          # 从 1.0 提升
}

reward_fn = make_reward(config)
```

### 如果你想鼓励快速完成：

```python
config = {
    "weights": {
        ...
        "step_penalty": 0.05,  # 每步减少 0.05 点
    }
}
```

### 如果非法动作的惩罚太强：

```python
config = {
    "weights": {
        ...
        "invalid_action_penalty": -0.5,  # 从 -1.0 改为 -0.5
    }
}
```

## 7️⃣ 从 YAML 配置加载

在 `configs/ppo_eco.yaml` 中添加：

```yaml
reward:
  weights:
    w_violation: 2.0
    w_min_voltage: 1.5
    w_mean_voltage: 0.5
    step_penalty: 0.0
    invalid_action_penalty: -1.0
  violation_scale: 10.0
  voltage_scale: 1.0
  clip_min: -5.0
  clip_max: 5.0
```

在代码中使用：

```python
import yaml
from rewards import make_reward

with open("configs/ppo_eco.yaml") as f:
    config = yaml.safe_load(f)

reward_fn = make_reward(config["reward"])
```

## 8️⃣ 调试技巧

### 打印奖励构成

```python
from rewards import VoltageOptimizationReward, RewardWeights

reward_fn = VoltageOptimizationReward()
reward = reward_fn.compute(info)

# 或者手动计算各部分
baseline = reward_fn.baseline_metrics
current = reward_fn.VoltageMetrics.from_info(info)

print(f"Δviolation: {baseline.violation_count - current.violation_count}")
print(f"Δmin_voltage: {current.min_voltage - baseline.min_voltage}")
print(f"Δmean_voltage: {current.mean_voltage - baseline.mean_voltage}")
```

### 验证环境返回的 info

```python
obs, info = env.reset()
reward_fn.reset()

obs, _, done, truncated, info = env.step(action)
print("info keys:", info.keys())
print("inst_voltage:", info.get("inst_voltage"))
print("violations:", info.get("violations"))
print("valid_action:", info.get("valid_action"))

reward = reward_fn.compute(info)
print("reward:", reward)
```

## 9️⃣ 常见问题

**Q: 为什么第一步奖励是 0？**
A: 第一步用来设置 baseline，无法对比，所以返回 0。第二步开始才有对比。

**Q: 如果 inst_voltage 列表为空怎么办？**
A: 会正常处理，min_voltage 和 mean_voltage 都为 0，不会报错。

**Q: 非法动作是什么时候返回？**
A: 当 `info["valid_action"] = False` 时，直接返回 `invalid_action_penalty`，不进行对比。

**Q: 能同时优化功耗和面积吗？**
A: 可以，在 `CompositeReward` 中扩展，目前只支持 voltage。

## 🔟 完整训练示例

```python
from rewards import make_reward
from algo.ppo import PPO

# 创建奖励函数
reward_cfg = {
    "weights": {
        "w_violation": 2.0,
        "w_min_voltage": 1.5,
        "w_mean_voltage": 0.5,
    },
    "violation_scale": 10.0,
    "voltage_scale": 1.0,
}
reward_fn = make_reward(reward_cfg)

# 训练
ppo = PPO(...)
for episode in range(num_episodes):
    obs, info = env.reset()
    reward_fn.reset()  # 重置 baseline
    
    for step in range(max_steps):
        action = ppo.select_action(obs)
        obs, _, done, truncated, info = env.step(action)
        
        reward = reward_fn.compute(info)  # 计算奖励
        ppo.record_step(obs, action, reward, done)
        
        if done or truncated:
            break
    
    ppo.update()  # 更新模型
```

---

**更多详情**：查看 `rewards/README.md` 和 `rewards/demo_reward.py`

