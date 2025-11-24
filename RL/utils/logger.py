# utils/logger.py
from __future__ import annotations
from typing import Any, Dict, Optional
import os, csv, datetime as dt

class TBLogger:
    def __init__(self, run_dir: Optional[str] = None, filename: str = "train_log.csv") -> None:
        # 如果没给 run_dir，就兜底一个默认目录
        self.run_dir = run_dir or "runs/eco_ppo_v0"
        os.makedirs(self.run_dir, exist_ok=True)

        self.csv_path = os.path.join(self.run_dir, filename)
        self._csv_header_written = False
        self.last: Dict[str, Any] = {}

        # 也打印一行方便你确认目录
        ts = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] Logger initialized at: {self.run_dir}")

    def log(self, scalars: Dict[str, Any], step: int | None = None) -> None:
        self.last.update(scalars)
        prefix = f"[step={step}] " if step is not None else ""
        print(prefix + ", ".join(f"{k}={v}" for k, v in scalars.items()))

        # 写 CSV（按第一次看到的字段顺序写表头，后续增量字段自动扩展）
        row = dict(scalars)
        if step is not None:
            row = {"step": step, **row}

        write_header = (not self._csv_header_written) or (not os.path.exists(self.csv_path))
        # 如果新来了字段，补齐表头（简单做法：重写表头）
        fieldnames = ["step"] if "step" in row else []
        for k in row.keys():
            if k != "step":
                fieldnames.append(k)

        # 读取旧头（如存在），合并字段
        if os.path.exists(self.csv_path) and not write_header:
            with open(self.csv_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                try:
                    old_header = next(reader)
                    # 合并老字段
                    for k in old_header:
                        if k not in fieldnames:
                            fieldnames.append(k)
                except StopIteration:
                    write_header = True

        # 追加写入
        file_exists = os.path.exists(self.csv_path)
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if write_header or not file_exists:
                writer.writeheader()
                self._csv_header_written = True
            writer.writerow(row)
