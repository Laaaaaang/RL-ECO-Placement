# envs/prepare_data.py
from __future__ import annotations
import os
from typing import Tuple, Dict, Any, Optional
import numpy as np

from .classifier import classify_raw_to_celltypes
from .eco_env import build_feature_tensor


def run(
    raw_path: str = os.path.join(os.path.dirname(__file__), "raw_data.csv"),
    out_dir: str = os.path.dirname(__file__),
    top_k: int = 128,
    sort_by: Optional[str] = None,
    stats_filename: str = "feature_stats.npz",
    features_filename: str = "features.npz",
    celltypes_filename: str = "celltypes.csv",
) -> Tuple[str, str, str, Dict[str, Any]]:
    """
    End-to-end data preparation pipeline:

    raw_data.csv  --(classifier)-->  celltypes.csv
    celltypes.csv --(feature builder + name mapping)--> features.npz (obs) + feature_stats.npz

    Returns:
        (raw_csv_path, celltypes_csv_path, features_npz_path, meta_dict)
    """
    if not os.path.exists(raw_path):
        raise FileNotFoundError(f"[prepare_data] raw_data not found: {raw_path}")

    os.makedirs(out_dir, exist_ok=True)

    cell_csv = os.path.join(out_dir, celltypes_filename)
    stats_npz = os.path.join(out_dir, stats_filename)
    features_npz = os.path.join(out_dir, features_filename)

    # 1) 分类：确保存在 celltype 与 celltype_id（如果缺失则占位生成）
    cell_csv = classify_raw_to_celltypes(raw_path, cell_csv)

    # 2) 特征构建：选择列 -> 数值化 -> 标准化(复用/拟合) -> Top-K+Mask -> 展平
    #    同时基于 raw_data.csv 做 (x,y) → instancename/cellname 的映射，写入 meta
    obs_vec, meta = build_feature_tensor(
        celltypes_csv=cell_csv,
        top_k=top_k,
        sort_by=sort_by,
        stats_path=stats_npz,
        raw_csv_path=raw_path,
    )

    # 3) 持久化观测向量（扁平化的一行 obs），供后续 Actor/Critic 使用
    np.savez(features_npz, obs=obs_vec.astype(np.float32))

    return raw_path, cell_csv, features_npz, meta


if __name__ == "__main__":
    # 简单命令行运行：python -m envs.prepare_data
    raw, cell, feat, meta = run()
    meta_shapes = {k: (v.shape if hasattr(v, "shape") else type(v).__name__) for k, v in meta.items()}
    print("[prepare_data] done")
    print("  raw     :", raw)
    print("  celltypes:", cell)
    print("  features :", feat)
    print("  meta keys:", list(meta.keys()))
    print("  meta shapes/types:", meta_shapes)
