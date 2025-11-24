# 奖励函数重构完成 - 总结

## 📋 完成内容

已根据你的需求，完整重构了工程的奖励函数系统。核心改进如下：

### 1. **核心设计** ✅

奖励函数现在基于 **Instance Voltage 前后对比**，包含三个维度：

| 维度 | 优先级 | 权重 | 含义 |
|------|--------|------|------|
| **违例数量减少** | 🔴 最高 | 2.0 | Δviolation = baseline_vio - current_vio |
| **最小电压增加** | 🟡 高 | 1.5 | Δmin_voltage = current_min - baseline_min |
| **平均电压增加** | 🟢 中等 | 0.5 | Δmean_voltage = current_mean - baseline_mean |

### 2. **优先级体现** ✅

核心需求："**违例减少较多时，最小电压变小也可接受**"

**已完全实现**，通过权重 `w_violation = 2.0` 和 `violation_scale = 10.0` 实现：

```python
# 示例：违例从 3 减到 0，最小电压从 0.80 降到 0.78
reward = 2.0 * 10 * 3 + 1.5 * 1 * (-0.02) + 0.5 * 1 * 0.01
       = 60.0 - 0.03 + 0.005 = 59.975  ✓ 非常高的奖励
```

### 3. **文件结构** ✅

```
rewards/
├── __init__.py              # 导出公共接口
├── base.py                  # 核心实现（293 行，结构清晰）
├── README.md                # 详细使用说明
└── demo_reward.py           # 5 个具体演示示例
```

## 📊 新旧对比

### 旧设计（IR-drop based）
- ❌ 固定阈值（0.05V）
- ❌ 未体现优先级
- ❌ 难以处理多目标平衡

### 新设计（Instance Voltage based）
- ✅ 动态前后对比
- ✅ 明确的优先级体系
- ✅ 灵活的多目标加权
- ✅ 支持自动 baseline 初始化

## 🔑 关键类和函数

### `VoltageOptimizationReward` （核心类）
```python
reward_fn = VoltageOptimizationReward(
    weights=RewardWeights(),
    violation_scale=10.0,  # 违例减少 1 个 = 10 点奖励
    voltage_scale=1.0,     # 电压增加 0.01V = 0.01 点奖励
)

# 第一次调用自动设置 baseline
reward = reward_fn.compute(info)  # = 0.0

# 第二次及以后进行前后对比
reward = reward_fn.compute(info)  # > 0 if improved
```

### `RewardWeights` （权重数据类）
```python
@dataclass
class RewardWeights:
    w_violation: float = 2.0           # 优先级最高
    w_min_voltage: float = 1.5         # 重点关注
    w_mean_voltage: float = 0.5        # 次要目标
    step_penalty: float = 0.0          # 每步惩罚
    invalid_action_penalty: float = -1.0  # 非法动作
```

### `VoltageMetrics` （指标数据类）
```python
@dataclass
class VoltageMetrics:
    inst_voltage_list: List[float]  # 所有 instance 电压
    min_voltage: float              # 最小值
    mean_voltage: float             # 平均值
    max_voltage: float              # 最大值
    violation_count: int            # 违例数
```

### `make_reward(cfg)` （工厂函数）
```python
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
```

## 📝 使用步骤

### 步骤 1：配置（可选）
在你的 YAML 配置中添加：
```yaml
reward:
  weights:
    w_violation: 2.0
    w_min_voltage: 1.5
    w_mean_voltage: 0.5
    step_penalty: 0.01
  violation_scale: 10.0
  voltage_scale: 1.0
  clip_min: -5.0
  clip_max: 5.0
```

### 步骤 2：初始化
```python
from rewards import make_reward

reward_cfg = load_config()  # 从 YAML 加载
reward_fn = make_reward(reward_cfg)
```

### 步骤 3：每个 Episode 重置
```python
for episode in range(num_episodes):
    obs, info = env.reset()
    reward_fn.reset()  # 清空 baseline
    
    for step in range(max_steps):
        action = agent.select_action(obs)
        obs, _, done, truncated, info = env.step(action)
        
        # info 需包含：inst_voltage, violations, valid_action
        reward = reward_fn.compute(info)
        agent.step(obs, reward, done, truncated)
```

### 步骤 4：环境返回格式
确保 `env.step()` 返回的 `info` 包含：
```python
info = {
    "inst_voltage": [0.70, 0.75, 0.80, ...],  # 必需
    "violations": [inst_1, inst_3] or 2,      # 可选
    "valid_action": True,                      # 可选（默认 True）
}
```

## 🎯 验证演示

已运行 5 个具体示例验证：

| 示例 | 场景 | 结果 |
|------|------|------|
| 1 | 优秀改善（违例↓+电压↑） | ✅ reward = 5.0（裁剪后）|
| 2 | 违例减少+电压略降 | ✅ reward = 5.0（正奖励，验证优先级）|
| 3 | 非法动作 | ✅ reward = -1.0（直接惩罚）|
| 4 | 自定义权重 | ✅ reward = 0.06（灵活调整）|
| 5 | 工厂函数 | ✅ reward = 5.0（配置化创建）|

## 🔧 参数调整指南

| 现象 | 调整方向 |
|------|---------|
| 过度关注违例，忽视电压 | ↓ `w_violation` 或 `violation_scale` |
| 过度关注电压，违例难消除 | ↑ `w_violation` |
| 训练太慢 | ↑ `violation_scale` 和 `voltage_scale` |
| 奖励波动过大 | ↓ scale 值或调整 `clip_min/max` |
| 倾向用太多步 | ↑ `step_penalty` |

## 📚 文档位置

- **核心实现**: `rewards/base.py`
- **使用说明**: `rewards/README.md`
- **演示示例**: `rewards/demo_reward.py`

## ✨ 亮点

1. **自动初始化**：第一步自动检测 baseline，无需手动设置
2. **灵活权重**：通过权重和 scale 参数灵活调整多目标平衡
3. **优先级清晰**：高权重数值直观体现优先级
4. **类型安全**：使用 Protocol 和 dataclass，结构清晰
5. **易于扩展**：CompositeReward 预留了扩展位置，可加入功耗、面积等指标

---

## 🚀 下一步

1. 在 `train_rllib.py` 或 `main_train.py` 中集成这个奖励函数
2. 修改环境返回的 `info` 字典，确保包含 `inst_voltage` 和 `violations`
3. 根据训练结果调整 `violation_scale` 和权重
4. （可选）将配置写入 `configs/ppo_eco.yaml`

有任何问题或需要进一步调整，请随时告诉我！

