# envs/mapping.py
from __future__ import annotations
from typing import List, Tuple, Dict, Optional
import numpy as np
import pandas as pd
import os

# 常见列名别名（容错）
NAME_ALIASES = {
    "cellname": ["cellname", "cell_name", "refcell", "ref_cell", "master", "macro", "lib_cell"],
    "instancename": ["instancename", "inst_name", "instance", "inst", "comp_name"],
    "x": ["x", "x_coord", "coord_x"],
    "y": ["y", "y_coord", "coord_y"],
}

def _pick_col(df: pd.DataFrame, keys: List[str]) -> Optional[str]:
    for k in keys:
        if k in df.columns: 
            return k
    return None

def map_names_by_xy(
    processed_df: pd.DataFrame,    # 已选列、已排序的 DataFrame（Top-K 之前）
    raw_csv_path: str,
    round_decimals: int = 3,       # 粗匹配：四舍五入到 1e-3 网格
    tol: float = 1e-4              # 精匹配：最近邻半径
) -> Tuple[List[str], List[str], List[float]]:
    """
    返回与 processed_df 同顺序的三个列表：
      instancename_list, cellname_list, match_dist_list
    先尝试四舍五入合并；未匹配上的再走最近邻（<= tol）。
    """
    if not os.path.exists(raw_csv_path):
        n = len(processed_df)
        return [""]*n, [""]*n, [float("inf")]*n

    raw = pd.read_csv(raw_csv_path)

    # 选列名（容错）
    x_p = _pick_col(processed_df, NAME_ALIASES["x"]) or "x"
    y_p = _pick_col(processed_df, NAME_ALIASES["y"]) or "y"
    x_r = _pick_col(raw, NAME_ALIASES["x"]) or "x"
    y_r = _pick_col(raw, NAME_ALIASES["y"]) or "y"

    inst_col = _pick_col(raw, NAME_ALIASES["instancename"])
    cell_col = _pick_col(raw, NAME_ALIASES["cellname"])

    # 初始化输出
    n = len(processed_df)
    inst_out = [""] * n
    cell_out = [""] * n
    dist_out = [float("inf")] * n

    # --- 粗匹配：四舍五入后 merge ---
    p = processed_df[[x_p, y_p]].copy()
    p["__rx"] = p[x_p].round(round_decimals)
    p["__ry"] = p[y_p].round(round_decimals)
    r = raw[[x_r, y_r]].copy()
    r["__rx"] = r[x_r].round(round_decimals)
    r["__ry"] = r[y_r].round(round_decimals)

    if inst_col: r["__inst"] = raw[inst_col].astype(str)
    if cell_col: r["__cell"] = raw[cell_col].astype(str)

    merged = p.merge(r[["__rx","__ry","__inst","__cell"]], on=["__rx","__ry"], how="left")

    for i in range(n):
        if pd.notna(merged.loc[i, "__inst"]) or pd.notna(merged.loc[i, "__cell"]):
            inst_out[i] = str(merged.loc[i, "__inst"]) if "__inst" in merged.columns and pd.notna(merged.loc[i, "__inst"]) else ""
            cell_out[i] = str(merged.loc[i, "__cell"]) if "__cell" in merged.columns and pd.notna(merged.loc[i, "__cell"]) else ""
            dist_out[i] = 0.0  # 粗匹配视作 0

    # --- 精匹配：对未命中的行做最近邻 ---
    unresolved_idx = [i for i,d in enumerate(dist_out) if not np.isfinite(d)]
    if len(unresolved_idx) > 0:
        P = processed_df.loc[unresolved_idx, [x_p, y_p]].to_numpy(dtype=np.float64)  # R x 2
        R = raw[[x_r, y_r]].to_numpy(dtype=np.float64)                              # M x 2
        if len(R) > 0:
            # 简单双循环最近邻（R 和 M 通常数量可控；若很大可换网格桶/分片）
            # 这里向量化计算全距：对 R 行开销可接受（top_k <= 1k 常见）
            d2 = ((P[:,None,:] - R[None,:,:])**2).sum(axis=2)  # (R, M)
            j_min = d2.argmin(axis=1)
            d_min = np.sqrt(d2[np.arange(len(unresolved_idx)), j_min])
            for k, row_i in enumerate(unresolved_idx):
                if d_min[k] <= tol:
                    j = int(j_min[k])
                    inst_out[row_i] = str(raw.iloc[j][inst_col]) if inst_col else inst_out[row_i]
                    cell_out[row_i] = str(raw.iloc[j][cell_col]) if cell_col else cell_out[row_i]
                    dist_out[row_i] = float(d_min[k])

    return inst_out, cell_out, dist_out
