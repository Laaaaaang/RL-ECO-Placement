# envs/eco_env.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import os
import numpy as np
import pandas as pd

# ============================================================
#  Feature schema (numerical columns you want to feed the model)
#  NOTE: treat all as numeric; string columns are factorized.
# ============================================================
NUMERIC_FEATURES: List[str] = [
    "x", "y", "w", "h",
    "inst_ploc_len1", "inst_ploc_len2", "inst_ploc_len3",
    "region_5x5_cell_num", "region_5x5_cell_density",
    "inst_voltage",
    "region_5x5_avg_ir", "region_5x5_min_ir", "region_5x5_max_ir",
    "celltype", "celltype_id",
]

# ============================================================
#  Helpers: numeric coercion + standardization
# ============================================================

def _coerce_numeric(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """
    Ensure all selected columns are numeric.
    - Missing columns are created with zeros.
    - Non-numeric columns are factorized deterministically to int64.
    """
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = 0.0
        if not pd.api.types.is_numeric_dtype(out[c]):
            tokens = out[c].astype(str).str.strip().str.lower().fillna("nan")
            codes, _ = pd.factorize(tokens, sort=True)
            out[c] = codes.astype("int64")
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out[cols]


def _fit_stats(X: np.ndarray) -> Dict[str, np.ndarray]:
    mean = X.mean(axis=0, keepdims=True)
    std = X.std(axis=0, keepdims=True)
    std = np.where(std < 1e-6, 1.0, std)  # avoid divide-by-zero
    return {"mean": mean.astype(np.float32), "std": std.astype(np.float32)}


def _apply_stats(X: np.ndarray, stats: Dict[str, np.ndarray]) -> np.ndarray:
    return (X - stats["mean"]) / stats["std"]


# ============================================================
#  Name mapping (Top-K rows  <->  raw_data.csv)
#  - coarse match: rounded (x,y) join
#  - refine: nearest neighbor within tolerance
# ============================================================

_NAME_ALIASES = {
    "cellname":      ["cellname", "cell_name", "refcell", "ref_cell", "master", "macro", "lib_cell"],
    "instancename":  ["instancename", "inst_name", "instance", "inst", "comp_name"],
    "x":             ["x", "x_coord", "coord_x"],
    "y":             ["y", "y_coord", "coord_y"],
}

def _pick_col(df: pd.DataFrame, keys: List[str]) -> Optional[str]:
    for k in keys:
        if k in df.columns:
            return k
    return None


def _map_names_by_xy(
    processed_df: pd.DataFrame,   # already filtered/sorted; BEFORE padding
    raw_csv_path: str,
    round_decimals: int = 3,
    tol: float = 1e-4,
) -> Tuple[List[str], List[str], List[float]]:
    """
    Return three lists aligned with processed_df rows:
      instancename_list, cellname_list, match_dist_list
    1) round-merge on (x,y) for coarse exact hits;
    2) nearest-neighbor (<= tol) for remaining rows.
    """
    n = len(processed_df)
    if n == 0 or not os.path.exists(raw_csv_path):
        return [""] * n, [""] * n, [float("inf")] * n

    raw = pd.read_csv(raw_csv_path)

    x_p = _pick_col(processed_df, _NAME_ALIASES["x"]) or "x"
    y_p = _pick_col(processed_df, _NAME_ALIASES["y"]) or "y"
    x_r = _pick_col(raw,          _NAME_ALIASES["x"]) or "x"
    y_r = _pick_col(raw,          _NAME_ALIASES["y"]) or "y"

    inst_col = _pick_col(raw, _NAME_ALIASES["instancename"])
    cell_col = _pick_col(raw, _NAME_ALIASES["cellname"])

    inst_out = [""] * n
    cell_out = [""] * n
    dist_out = [float("inf")] * n

    # ---- coarse match by rounded coordinates
    p = processed_df[[x_p, y_p]].copy()
    p["__rx"] = p[x_p].round(round_decimals)
    p["__ry"] = p[y_p].round(round_decimals)

    r = raw[[x_r, y_r]].copy()
    r["__rx"] = r[x_r].round(round_decimals)
    r["__ry"] = r[y_r].round(round_decimals)
    if inst_col: r["__inst"] = raw[inst_col].astype(str)
    if cell_col: r["__cell"] = raw[cell_col].astype(str)

    merged = p.merge(r[["__rx", "__ry", "__inst", "__cell"]], on=["__rx", "__ry"], how="left")

    for i in range(n):
        inst_val = merged.loc[i, "__inst"] if "__inst" in merged.columns else np.nan
        cell_val = merged.loc[i, "__cell"] if "__cell" in merged.columns else np.nan
        if pd.notna(inst_val) or pd.notna(cell_val):
            inst_out[i] = str(inst_val) if pd.notna(inst_val) else ""
            cell_out[i] = str(cell_val) if pd.notna(cell_val) else ""
            dist_out[i] = 0.0  # coarse match

    # ---- nearest neighbor for unresolved rows
    unresolved = [i for i, d in enumerate(dist_out) if not np.isfinite(d)]
    if len(unresolved) > 0 and len(raw) > 0:
        P = processed_df.loc[unresolved, [x_p, y_p]].to_numpy(dtype=np.float64)  # R x 2
        R = raw[[x_r, y_r]].to_numpy(dtype=np.float64)                           # M x 2
        if R.size > 0:
            # pairwise distance (R may be large but top_k is typically manageable)
            d2 = ((P[:, None, :] - R[None, :, :]) ** 2).sum(axis=2)              # (R, M)
            j_min = d2.argmin(axis=1)
            d_min = np.sqrt(d2[np.arange(len(unresolved)), j_min])
            for k, row_i in enumerate(unresolved):
                if d_min[k] <= tol:
                    j = int(j_min[k])
                    if inst_col:
                        inst_out[row_i] = str(raw.iloc[j][inst_col])
                    if cell_col:
                        cell_out[row_i] = str(raw.iloc[j][cell_col])
                    dist_out[row_i] = float(d_min[k])

    return inst_out, cell_out, dist_out


# ============================================================
#  Feature builder: celltypes.csv  ->  flattened obs + meta
#  - numeric coercion
#  - (optional) sorting
#  - top_k + padding + mask
#  - standardization (fit/save or load)
#  - name mapping from raw_data.csv
# ============================================================

def build_feature_tensor(
    celltypes_csv: str,
    *,
    top_k: int = 128,
    sort_by: Optional[str] = None,
    stats_path: Optional[str] = None,
    raw_csv_path: Optional[str] = None,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Returns:
      obs_vec: (top_k * (F + 1),) float32    # +1 for presence mask
      meta: {
        "top_k", "feature_dim", "with_mask", "taken", "padded",
        "stats": {"mean","std"},
        "orig_xy": (top_k,2),
        "x_range": (xmin,xmax), "y_range": (ymin,ymax),
        "instancename": [top_k], "cellname": [top_k], "match_dist": [top_k]
      }
    """
    df = pd.read_csv(celltypes_csv)
    Xdf = _coerce_numeric(df, NUMERIC_FEATURES)

    # Keep df and Xdf aligned for optional sorting
    if sort_by is not None and sort_by in Xdf.columns:
        Xdf = Xdf.sort_values(sort_by, ascending=False)
        df = df.loc[Xdf.index]

    # Top-K slice (before padding)
    F = Xdf.shape[1]
    take = min(top_k, len(Xdf))
    pad = top_k - take

    X_top = Xdf.iloc[:take]  # not yet standardized
    X = X_top.to_numpy(dtype=np.float32)
    if pad > 0:
        X = np.vstack([X, np.zeros((pad, F), dtype=np.float32)])

    # stats: load or fit
    if stats_path and os.path.exists(stats_path):
        stats_npz = dict(np.load(stats_path))
        stats = {"mean": stats_npz["mean"], "std": stats_npz["std"]}
    else:
        stats = _fit_stats(X)
        if stats_path:
            os.makedirs(os.path.dirname(stats_path), exist_ok=True)
            np.savez(stats_path, **stats)

    Xn = _apply_stats(X, stats)

    # presence mask channel
    mask = np.zeros((top_k, 1), dtype=np.float32)
    mask[:take, 0] = 1.0

    Xn_masked = np.concatenate([Xn, mask], axis=1)  # (top_k, F+1)
    obs_vec = Xn_masked.reshape(-1).astype(np.float32)

    # original coordinates and ranges (from unstandardized Xdf)
    orig_xy = X_top[["x", "y"]].to_numpy(dtype=np.float32)
    if pad > 0:
        orig_xy = np.vstack([orig_xy, np.zeros((pad, 2), dtype=np.float32)])

    x_min, x_max = float(Xdf["x"].min()), float(Xdf["x"].max())
    y_min, y_max = float(Xdf["y"].min()), float(Xdf["y"].max())

    # names mapping (instancename, cellname), aligned with Top-K order
    inst_list = [""] * top_k
    cell_list = [""] * top_k
    dist_list = [float("inf")] * top_k
    if raw_csv_path is not None:
        inst_top, cell_top, dist_top = _map_names_by_xy(X_top.reset_index(drop=True), raw_csv_path)
        for i in range(take):
            inst_list[i] = inst_top[i]
            cell_list[i] = cell_top[i]
            dist_list[i] = dist_top[i]

    meta: Dict[str, Any] = {
        "top_k": top_k,
        "feature_dim": F,
        "with_mask": True,
        "taken": int(take),
        "padded": int(pad),
        "stats": {"mean": stats["mean"], "std": stats["std"]},
        "orig_xy": orig_xy,                  # (top_k, 2)
        "x_range": (x_min, x_max),
        "y_range": (y_min, y_max),
        "instancename": inst_list,           # [top_k] strings (may be "")
        "cellname": cell_list,               # [top_k] strings (may be "")
        "match_dist": dist_list,             # [top_k] float; 0=rounded hit; >0=NN distance; inf=unmatched
    }
    return obs_vec, meta


# ============================================================
#  Discrete grid -> absolute coordinate (bin center)
# ============================================================

def decode_xy_from_bins(
    x_bin: int,
    y_bin: int,
    x_bins: int,
    y_bins: int,
    x_range: Tuple[float, float],
    y_range: Tuple[float, float],
) -> Tuple[float, float]:
    x0, x1 = x_range
    y0, y1 = y_range
    # map to bin center
    tx = x0 + (x_bin + 0.5) * (x1 - x0) / max(1, x_bins)
    ty = y0 + (y_bin + 0.5) * (y1 - y0) / max(1, y_bins)
    return float(tx), float(ty)


# ============================================================
#  Minimal placeholder Env (kept for integration)
#  - action format: [cell_idx, x_bin, y_bin]
#  - _decode_action returns the full 6-tuple info payload
# ============================================================

class EcoEnv:
    """
    Minimal placeholder RL env so the rest of the pipeline can import/run.
    You can later replace step/reset with the real sign-off/tool calls.
    """
    def __init__(
        self,
        obs_dim: int,
        action_dims: Optional[List[int]] = None,   # e.g., [top_k, x_bins, y_bins]
        meta: Optional[Dict[str, Any]] = None,     # returned by build_feature_tensor
        raw_csv_path: str = "./envs/raw_data.csv",
        max_steps: int = 10,
    ) -> None:
        self._obs_dim = int(obs_dim)
        self._action_dims = action_dims or [4, 3, 3]
        self._step_count = 0
        self._max_steps = int(max_steps)
        self.meta = meta or {}
        self.raw_csv_path = raw_csv_path
        self.placed_xy: List[Tuple[float, float, float, float]] = []  # [(x, y, w, h)]

    @property
    def observation_space_shape(self) -> Tuple[int]:
        return (self._obs_dim,)

    @property
    def action_space_nvec(self) -> np.ndarray:
        return np.array(self._action_dims, dtype=np.int64)

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        self._step_count = 0
        self.placed_xy = []  # 每次重置清空已放置列表
        rng = np.random.default_rng(seed)
        obs = rng.standard_normal(self._obs_dim, dtype=np.float32)
        return obs, {}

    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        """
        Placeholder transition. Real implementation should:
          - apply the ECO move decoded from action
          - get new obs from updated design
          - compute reward from sign-off metrics
        """
        self._step_count += 1

        # 自动选取 inst_voltage 最低的 instance
        voltage_list = self.meta.get("inst_voltage", None)
        if voltage_list is not None and len(voltage_list) > 0:
            min_idx = int(np.argmin(voltage_list))
            # 保证动作的 cell_idx 为最低电压 instance
            action = np.asarray(action, dtype=np.int64)
            action[0] = min_idx

        # dummy next obs/reward
        obs = np.zeros(self._obs_dim, dtype=np.float32)
        reward = float(np.random.uniform(-0.1, 0.1))
        terminated = self._step_count >= self._max_steps
        truncated = False
        info: Dict[str, Any] = self._decode_action(action)
        return obs, reward, terminated, truncated, info

    # ----------------------------
    #  Action decoder (the key)
    # ----------------------------
    def _decode_action(self, action: np.ndarray) -> Dict[str, Any]:
        """
        Convert MultiDiscrete action [cell_idx, x_bin, y_bin] into:
          {
            "cell_idx": int,
            "instancename": str,
            "cellname": str,
            "orig_x": float, "orig_y": float,
            "target_x": float, "target_y": float,
            "match_dist": float
          }
        """
        a = np.asarray(action, dtype=np.int64).tolist()
        if len(a) < 3:
            raise ValueError(f"Expect action with 3 heads [cell_idx, x_bin, y_bin], got: {a}")
        cell_idx, x_bin, y_bin = int(a[0]), int(a[1]), int(a[2])

        # Original coordinates
        orig_xy = self.meta.get("orig_xy", None)
        if orig_xy is None or cell_idx >= len(orig_xy):
            orig_x, orig_y = 0.0, 0.0
        else:
            orig_x = float(orig_xy[cell_idx, 0])
            orig_y = float(orig_xy[cell_idx, 1])

        # Decode target coordinates from bins (absolute grid)
        x_bins = int(self._action_dims[1])
        y_bins = int(self._action_dims[2])
        tx, ty = decode_xy_from_bins(
            x_bin, y_bin, x_bins, y_bins,
            self.meta.get("x_range", (0.0, 1.0)),
            self.meta.get("y_range", (0.0, 1.0)),
        )

        # Instance/cell names (pre-mapped in meta by build_feature_tensor)
        inames = self.meta.get("instancename", [])
        cnames = self.meta.get("cellname", [])
        dists  = self.meta.get("match_dist", [])

        instancename = str(inames[cell_idx]) if (cell_idx < len(inames) and inames[cell_idx] is not None) else ""
        cellname     = str(cnames[cell_idx]) if (cell_idx < len(cnames) and cnames[cell_idx] is not None) else ""
        match_dist   = float(dists[cell_idx]) if (cell_idx < len(dists)) else float("inf")

        # 获取 instance 的尺寸 w, h
        w_list = self.meta.get("w", None)
        h_list = self.meta.get("h", None)
        if w_list is not None and cell_idx < len(w_list):
            inst_w = float(w_list[cell_idx])
        else:
            inst_w = 0.0
        if h_list is not None and cell_idx < len(h_list):
            inst_h = float(h_list[cell_idx])
        else:
            inst_h = 0.0

        # die 范围限制（从 meta 读取，若无则默认极大值）
        die_size_x = self.meta.get("die_size_x", 1e9)
        die_size_y = self.meta.get("die_size_y", 1e9)

        # 边界判断
        in_die = (0 <= tx <= die_size_x-inst_w) and (0 <= ty <= die_size_y-inst_h)

        # 碰撞检测：遍历所有已放置 instance，判断是否重叠
        collision = False
        for px, py, pw, ph in getattr(self, 'placed_xy', []):
            if not (tx + inst_w <= px or px + pw <= tx or ty + inst_h <= py or py + ph <= ty):
                collision = True
                break

        valid = in_die and not collision

        return {
            "cell_idx": cell_idx,
            "instancename": instancename,
            "cellname": cellname,
            "orig_x": orig_x, "orig_y": orig_y,
            "target_x": tx,   "target_y": ty,
            "match_dist": match_dist,
            "w": inst_w,
            "h": inst_h,
            "collision": collision,
            "in_die": in_die,
            "valid": valid,
        }
