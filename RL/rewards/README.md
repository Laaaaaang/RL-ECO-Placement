# 奖励函数使用说明

## 概述

新的奖励函数 `VoltageOptimizationReward` 基于 **instance voltage 前后对比**，按以下优先级设计：

1. **优先级最高**：违例数量减少 (w_violation = 2.0)
2. **重点关注**：最小电压增加 (w_min_voltage = 1.5)
3. **次要目标**：平均电压增加 (w_mean_voltage = 0.5)

## 核心设计

### 维度对比

每一步计算三个改善维度：

```
Δ violation     = baseline_violation_count - current_violation_count
Δ min_voltage   = current_min_voltage - baseline_min_voltage
Δ mean_voltage  = current_mean_voltage - baseline_mean_voltage
```

### 奖励计算

```python
reward = w_violation * violation_scale * Δviolation
       + w_min_voltage * voltage_scale * Δmin_voltage
       + w_mean_voltage * voltage_scale * Δmean_voltage
       - step_penalty
```

### 优先级体现

**当违例减少较多时，即使最小电压有所下降也是可接受的：**

例如，若：
- 违例从 3 减少到 1 （Δviolation = 2）
- 最小电压从 0.80V 降到 0.75V （Δmin_voltage = -0.05）
- 平均电压从 0.90V 升到 0.92V （Δmean_voltage = 0.02）
- violation_scale = 10.0，voltage_scale = 1.0

则奖励为：
```
reward = 2.0 * 10.0 * 2 + 1.5 * 1.0 * (-0.05) + 0.5 * 1.0 * 0.02
       = 40.0 - 0.075 + 0.01
       = 39.935  （大正数，很好！）
```

即使最小电压下降，也因为违例大幅减少而获得高奖励。

## 使用方式

### 方式 1：自动初始化（推荐）

```python
from rewards.base import make_reward, RewardWeights

# 创建奖励函数（使用默认权重）
reward_fn = make_reward()

# 每个 step 直接调用
reward = reward_fn.compute(info)
# 第一次自动将 info 设为 baseline，后续进行对比
```

### 方式 2：显式控制

```python
from rewards.base import VoltageOptimizationReward, RewardWeights

# 自定义权重
weights = RewardWeights(
    w_violation=2.0,
    w_min_voltage=1.5,
    w_mean_voltage=0.5,
    step_penalty=0.01,
)

reward_fn = VoltageOptimizationReward(
    weights=weights,
    violation_scale=10.0,  # 违例减少 1 个 = 10 点奖励
    voltage_scale=1.0,     # 电压增加 0.01V = 0.01 点奖励
)

# 每个 episode 开始时重置
for episode in range(num_episodes):
    reward_fn.reset()  # 清空 baseline
    for step in range(max_steps):
        info = env.step(action)
        reward = reward_fn.compute(info)
```

### 方式 3：配置字典创建

```python
from rewards.base import make_reward

reward_cfg = {
    "weights": {
        "w_violation": 2.0,
        "w_min_voltage": 1.5,
        "w_mean_voltage": 0.5,
        "step_penalty": 0.01,
        "invalid_action_penalty": -1.0,
    },
    "violation_scale": 10.0,
    "voltage_scale": 1.0,
    "clip_min": -5.0,
    "clip_max": 5.0,
}

reward_fn = make_reward(reward_cfg)
reward = reward_fn.compute(info)
```

## Info 字典格式

环境返回的 `info` 字典需要包含以下字段（示例）：

```python
info = {
    # 必需：电压列表（浮点数列表）
    "inst_voltage": [0.80, 0.85, 0.90, 0.88, 0.75, ...],
    
    # 可选：违例信息（可以是列表或数字）
    "violations": [inst_1, inst_3],  # 或 "violation_count": 2
    
    # 可选：动作合法性（默认 True）
    "valid_action": True,
}
```

如果 `valid_action` 为 `False`，直接返回 `invalid_action_penalty`（默认 -1.0），不进行前后对比。

## 数值示例

### 示例 1：优秀的改善

初始状态（baseline）：
- `inst_voltage = [0.70, 0.75, 0.80, 0.85, 0.90]`
- `min_voltage = 0.70V`
- `mean_voltage = 0.80V`
- `violations = 2`

动作后：
- `inst_voltage = [0.75, 0.78, 0.82, 0.87, 0.92]`
- `min_voltage = 0.75V`
- `mean_voltage = 0.828V`
- `violations = 0`

计算奖励（默认参数）：
```
Δviolation = 2 - 0 = 2
Δmin_voltage = 0.75 - 0.70 = 0.05
Δmean_voltage = 0.828 - 0.80 = 0.028

reward = 2.0 * 10.0 * 2 + 1.5 * 1.0 * 0.05 + 0.5 * 1.0 * 0.028
       = 40.0 + 0.075 + 0.014
       = 40.089  （优秀！）
```

### 示例 2：违例减少但电压略降

初始状态：
- `min_voltage = 0.80V`
- `mean_voltage = 0.90V`
- `violations = 3`

动作后：
- `min_voltage = 0.78V`（略降）
- `mean_voltage = 0.92V`（增加）
- `violations = 0`（大幅减少）

计算奖励：
```
Δviolation = 3 - 0 = 3
Δmin_voltage = 0.78 - 0.80 = -0.02
Δmean_voltage = 0.92 - 0.90 = 0.02

reward = 2.0 * 10.0 * 3 + 1.5 * 1.0 * (-0.02) + 0.5 * 1.0 * 0.02
       = 60.0 - 0.03 + 0.01
       = 59.98  （仍然很好！）
```

即使最小电压下降，由于违例大幅减少，整体奖励仍然为正且较高。

## 参数调整建议

如果训练效果不理想，可以尝试：

| 现象 | 调整方向 |
|------|---------|
| 过度关注违例，忽视电压 | 降低 `w_violation` 或 `violation_scale` |
| 过度关注电压，违例难以消除 | 提高 `w_violation` |
| 训练太慢 | 提高 `violation_scale` 和 `voltage_scale` |
| 奖励波动过大 | 降低 `violation_scale`/`voltage_scale` 或调整 `clip_min/max` |
| 智能体倾向于用很多步 | 提高 `step_penalty` |

## 类结构

```
IReward (Protocol)
├── VoltageOptimizationReward (核心实现)
└── CompositeReward (复合，目前只用 Voltage)

RewardWeights (数据类，存储权重)
VoltageMetrics (数据类，存储某时刻的电压及违例指标)

make_reward(cfg) -> CompositeReward (工厂函数)
```

## 与环境集成

在训练循环中的使用模式：

```python
from rewards.base import make_reward

reward_cfg = {...}  # 从 YAML 配置加载
reward_fn = make_reward(reward_cfg)

for episode in range(num_episodes):
    obs, info = env.reset()
    reward_fn.reset()  # 重置 baseline
    
    for step in range(max_steps):
        action = agent.select_action(obs)
        obs, _, done, truncated, info = env.step(action)
        
        # 计算奖励
        reward = reward_fn.compute(info)
        
        # info 应包含: inst_voltage, violations, valid_action
        agent.step(obs, reward, done, truncated)
        
        if done or truncated:
            break
```

---

有任何问题或需要进一步调整，请告诉我！
