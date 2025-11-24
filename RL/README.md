# RL-based ECO Placement Optimization

A reinforcement learning framework for optimizing electronic circuit placement using the Proximal Policy Optimization (PPO) algorithm, with focus on minimizing IR-drop violations and improving voltage stability.

## 📋 Project Overview

This project implements a RL-based approach to solve the electronic circuit placement optimization problem, where the goal is to:
- **Minimize IR-drop violations** (highest priority)
- **Increase minimum voltage** in the circuit
- **Improve average voltage** stability

The framework uses **Instance Voltage metrics** to calculate rewards based on the before/after comparison of each action.

## 🎯 Key Features

- **Multi-objective Reward Design**: Hierarchical priority system (violations > min_voltage > mean_voltage)
- **Dynamic Baseline Comparison**: Automatic initial state tracking for fair before/after evaluation
- **Flexible Configuration**: YAML-based configuration for easy hyperparameter tuning
- **Modular Architecture**: Separated concerns for environment, algorithm, and reward computation
- **Comprehensive Documentation**: Detailed usage guides and examples

## 📁 Project Structure

```
RL/
├── algo/                          # RL algorithms
│   ├── __init__.py
│   ├── advantages.py              # Advantage calculation
│   ├── losses.py                  # PPO loss functions
│   ├── ppo.py                     # PPO implementation
│   └── storage.py                 # Experience replay buffer
│
├── envs/                          # Environment definitions
│   ├── __init__.py
│   ├── eco_env.py                 # Main ECO environment
│   ├── mock_env.py                # Mock environment for testing
│   ├── classifier.py              # Cell type classification
│   ├── mapping.py                 # Name mapping utilities
│   ├── prepare_data.py            # Data preparation
│   └── *.csv / *.npz              # Feature and cell data
│
├── nets/                          # Neural network architectures
│   ├── __init__.py
│   └── actor_critic.py            # Actor-Critic network
│
├── rewards/                       # Reward function system (NEWLY REFACTORED)
│   ├── __init__.py
│   ├── base.py                    # Core reward implementation
│   ├── README.md                  # Detailed reward documentation
│   └── demo_reward.py             # Usage examples
│
├── configs/                       # Configuration files
│   ├── __init__.py
│   └── ppo_eco.yaml               # PPO hyperparameters
│
├── utils/                         # Utilities
│   ├── __init__.py
│   ├── config.py                  # Configuration loading
│   └── logger.py                  # Logging utilities
│
├── mockgame/                      # Mock demos
│   └── move_instance_demo.py
│
├── main_train.py                  # Main training script
├── train_rllib.py                 # RLlib integration
├── REWARD_QUICKSTART.md           # Quick start guide for rewards
├── REWARD_REFACTOR_SUMMARY.md     # Reward system improvements
└── README.md                      # This file
```

## 🚀 Quick Start

### 1. Setup Environment

```bash
# Create conda environment with GPU support
conda create -n rl-eco python=3.10
conda activate rl-eco

# Install dependencies
pip install numpy pandas torch pyyaml gymnasium
```

### 2. Prepare Data

```bash
cd envs
python prepare_data.py
cd ..
```

### 3. Run Training

```bash
python main_train.py
```

Or with RLlib:
```bash
python train_rllib.py
```

## 🎓 Reward System (NEW)

The reward function has been completely redesigned to provide clear priority levels:

### Core Formula

```
reward = w_violation * violation_scale * Δviolation
       + w_min_voltage * voltage_scale * Δmin_voltage  
       + w_mean_voltage * voltage_scale * Δmean_voltage
       - step_penalty
```

### Default Weights

| Metric | Weight | Priority | Effect |
|--------|--------|----------|--------|
| Violation Reduction | 2.0 | 🔴 Highest | -1 violation = +20 points |
| Min Voltage Increase | 1.5 | 🟡 High | +0.01V = +0.015 points |
| Mean Voltage Increase | 0.5 | 🟢 Medium | +0.01V = +0.005 points |

### Example

When violations drop from 3 to 0 but min_voltage decreases by 0.02V:
```
reward = 2.0 * 10 * 3 + 1.5 * 1 * (-0.02) + ...
       = 60 - 0.03 + ... = 59.97  ✅ Still highly rewarded!
```

**This validates the priority: large violation reduction makes up for minor voltage decrease.**

### Quick Usage

```python
from rewards import make_reward

# Create reward function
reward_fn = make_reward()

# In training loop
for episode in range(num_episodes):
    obs, info = env.reset()
    reward_fn.reset()  # Reset baseline
    
    for step in range(max_steps):
        action = agent.select_action(obs)
        obs, _, done, truncated, info = env.step(action)
        
        # Info must contain: inst_voltage, violations, valid_action
        reward = reward_fn.compute(info)
        agent.step(obs, reward, done, truncated)
```

📖 **Full Documentation**: See [`rewards/README.md`](rewards/README.md) and [`REWARD_QUICKSTART.md`](REWARD_QUICKSTART.md)

## 🔧 Configuration

Edit `configs/ppo_eco.yaml` to customize:

```yaml
# Reward configuration
reward:
  weights:
    w_violation: 2.0          # Violation reduction weight
    w_min_voltage: 1.5        # Min voltage increase weight
    w_mean_voltage: 0.5       # Mean voltage increase weight
    step_penalty: 0.0         # Per-step penalty

# PPO hyperparameters
ppo:
  learning_rate: 3e-4
  gamma: 0.99
  gae_lambda: 0.95
  clip_ratio: 0.2
  epochs: 10
  batch_size: 64
```

## 📊 Supported Environments

- **EcoEnv**: Main placement optimization environment
- **MockEnv**: Simplified mock environment for testing
- **Custom**: Easy to extend with your own environment

## 📚 Key Files

| File | Purpose |
|------|---------|
| `main_train.py` | Main entry point for training |
| `algo/ppo.py` | PPO algorithm implementation |
| `envs/eco_env.py` | ECO placement environment |
| `nets/actor_critic.py` | Actor-Critic network architecture |
| `rewards/base.py` | **NEW**: Refactored reward system |
| `REWARD_QUICKSTART.md` | **NEW**: Reward usage guide |

## 🧪 Testing

Run the reward system demo:

```bash
cd rewards
python demo_reward.py
cd ..
```

Expected output: 5 test cases with detailed reward calculations ✅

## 📈 Performance Metrics

The training loop tracks:
- Episode return
- Policy loss
- Value loss
- Average reward per step
- Violation count over time
- Voltage statistics

## 🔄 Recent Updates

### Reward System Refactor (Latest)

**Before**: Fixed IR-drop threshold with limited priority control
**After**: Dynamic voltage comparison with explicit 3-level priority hierarchy

✅ Fully backward compatible  
✅ Improved documentation  
✅ Comprehensive examples  
✅ Verified with 5 test cases

**Migration**: Simply use `make_reward()` with optional config dict

## 💡 Example: Using Custom Weights

```python
from rewards import make_reward

# Emphasize voltage over violations
config = {
    "weights": {
        "w_violation": 1.0,        # Lower
        "w_min_voltage": 2.5,      # Higher
        "w_mean_voltage": 1.5,
    },
    "violation_scale": 5.0,
    "voltage_scale": 2.0,
}

reward_fn = make_reward(config)
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 📞 Support

For questions or issues:
1. Check existing documentation in `rewards/README.md`
2. Run the demo: `python rewards/demo_reward.py`
3. Review example configurations in `configs/`

## 🎯 Future Work

- [ ] Multi-objective optimization (power, area, timing)
- [ ] Distributed training with RLlib
- [ ] Real layout integration
- [ ] Visualization dashboard
- [ ] Hardware acceleration support

---

**Last Updated**: November 2025  
**Status**: Active Development
