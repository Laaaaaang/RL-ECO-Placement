import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 读取原始数据
df = pd.read_csv('./envs/raw_data.csv')

# 获取所有 instance 信息
instances = df[['inst_name', 'x', 'y', 'w', 'h', 'inst_voltage']].copy()

# 找到最低电压的 instance
min_idx = instances['inst_voltage'].idxmin()
min_instance = instances.loc[min_idx]

# 建议缩放因子（可根据实际情况调整）
SCALE = 100

# 坐标和尺寸缩放
instances['x'] = (instances['x'] // SCALE).astype(int)
instances['y'] = (instances['y'] // SCALE).astype(int)
instances['w'] = (instances['w'] // SCALE).clip(lower=1).astype(int)
instances['h'] = (instances['h'] // SCALE).clip(lower=1).astype(int)

# 重新计算 layout 边界
x_max = (instances['x'] + instances['w']).max()
y_max = (instances['y'] + instances['h']).max()
layout = np.zeros((int(y_max)+1, int(x_max)+1), dtype=np.int32)

# 标记所有 instance 占据的区域
for _, row in instances.iterrows():
    x0, y0, w, h = int(row['x']), int(row['y']), int(row['w']), int(row['h'])
    layout[y0:y0+h, x0:x0+w] = 1

# 可视化原始 layout（高亮最低电压 instance）

# 全局视图，蓝色高亮最低电压 instance
plt.figure(figsize=(12, 8))
plt.imshow(layout, origin='lower', cmap='Greys')
x0, y0, inst_w, inst_h = int(min_instance['x']), int(min_instance['y']), int(min_instance['w']), int(min_instance['h'])
rect = plt.Rectangle((x0, y0), inst_w, inst_h, linewidth=2, edgecolor='blue', facecolor='none')
plt.gca().add_patch(rect)
plt.text(x0+inst_w//2, y0+inst_h//2, 'Old Position', color='blue', fontsize=10, ha='center', va='center', fontweight='bold', bbox=dict(facecolor='white', alpha=0.6, edgecolor='blue'))
plt.title('Original Layout (Blue: To Move)')
plt.xlabel('X')
plt.ylabel('Y')
plt.tight_layout()
plt.show()

# 计算空位区域
empty = (layout == 0).astype(np.int32)

# 找到第一个足够大的空位区域（简单策略：从左下角开始扫描）
inst_w, inst_h = int(min_instance['w']), int(min_instance['h'])
found = False
for y in range(layout.shape[0] - inst_h):
    for x in range(layout.shape[1] - inst_w):
        region = empty[y:y+inst_h, x:x+inst_w]
        if np.all(region == 1):
            target_x, target_y = x, y
            found = True
            break
    if found:
        break

if not found:
    print('没有找到合适的空位！')
else:
    # 移动 instance 到目标位置
    # 清除原位置
    x0, y0 = int(min_instance['x']), int(min_instance['y'])
    layout[y0:y0+inst_h, x0:x0+inst_w] = 0
    # 标记新位置
    layout[target_y:target_y+inst_h, target_x:target_x+inst_w] = 2  # 用2表示新位置

    # 全局视图，红色高亮新位置
    plt.figure(figsize=(12, 8))
    plt.imshow(layout, origin='lower', cmap='Greys')
    rect_new = plt.Rectangle((target_x, target_y), inst_w, inst_h, linewidth=2, edgecolor='red', facecolor='none')
    plt.gca().add_patch(rect_new)
    plt.text(target_x+inst_w//2, target_y+inst_h//2, 'New Position', color='red', fontsize=10, ha='center', va='center', fontweight='bold', bbox=dict(facecolor='white', alpha=0.6, edgecolor='red'))
    # 箭头从旧位置指向新位置
    plt.arrow(x0+inst_w//2, y0+inst_h//2, target_x-x0, target_y-y0, color='green', width=0.5, head_width=3, length_includes_head=True)
    plt.title(f'Move Instance: {min_instance["inst_name"]}\nBlue: Old, Red: New')
    plt.xlabel('X')
    plt.ylabel('Y')
    plt.tight_layout()
    plt.show()
