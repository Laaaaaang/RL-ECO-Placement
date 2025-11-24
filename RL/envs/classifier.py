# envs/classifier.py
from __future__ import annotations
import re
import pandas as pd
from dataclasses import dataclass
from typing import List, Tuple

# ---------- Regex helpers ----------
VT_RE = re.compile(r'(ULVT|LVT|SVT|HVT)$', re.IGNORECASE)
PROC_SUFFIX_RE = re.compile(r'(?:BWP[0-9A-Z]+|[BP][A-Z0-9]{2,}\d*)$', re.IGNORECASE)
DRIVE_TAIL_RE = re.compile(r'(\d+)$')
UNDERSCORE_RE = re.compile(r'[_\-]')

def normalize_name(s: str) -> str:
    s = str(s).strip().upper()
    m_vt = VT_RE.search(s)
    if m_vt:
        s = s[:m_vt.start()]
    s = PROC_SUFFIX_RE.sub("", s)
    s = UNDERSCORE_RE.sub("", s)
    return s

def strip_drive_digits(base: str) -> Tuple[str, int | None]:
    m = DRIVE_TAIL_RE.search(base)
    if m:
        return base[:m.start()], int(m.group(1))
    return base, None

# ---------- Pattern library ----------
PATTERNS: List[Tuple[re.Pattern, callable]] = [
    (re.compile(r'^(AOI)(\d{2,3})$'), lambda m: "AOI"),
    (re.compile(r'^(OAI)(\d{2,3})$'), lambda m: "OAI"),
    (re.compile(r'^(NAND)(\d+)$'),    lambda m: "NAND"),
    (re.compile(r'^(NOR)(\d+)$'),     lambda m: "NOR"),
    (re.compile(r'^(AND)(\d+)$'),     lambda m: "AND"),
    (re.compile(r'^(OR)(\d+)$'),      lambda m: "OR"),
    (re.compile(r'^(XOR)(\d+)$'),     lambda m: "XOR"),
    (re.compile(r'^(XNOR)(\d+)$'),    lambda m: "XNOR"),
    (re.compile(r'^(MUXI?\d+|MXT?\d+)$'), lambda m: "MUX"),
    (re.compile(r'^(MUX)(\d+)$'),        lambda m: "MUX"),
    (re.compile(r'^(INV|INVD|INVX)$'),   lambda m: "INV"),
    (re.compile(r'^(BUF|BUFF|BUFX|IBUF|TBUF)$'), lambda m: "BUF"),
    (re.compile(r'^(CLKBUF|CKBD)$'),    lambda m: "CLKBUF"),
    (re.compile(r'^(CLKINV|CKINV)$'),   lambda m: "CLKINV"),
    (re.compile(r'^(ICG|CLKGATE|CLKGATETST[A-Z]*)$'), lambda m: "ICG"),
    (re.compile(r'^(SDFF|DFFQ?|DFQD|DFFC|DFFR[ES]?|DFFS[ER]?|DFFN|QDFRBN)$'), lambda m: "DFF"),
    (re.compile(r'^(LAT|LATCH|DLH|DLL|LHQD?)$'), lambda m: "LATCH"),
    (re.compile(r'^(ISO|ISOL|ISOLAND)$'), lambda m: "ISO"),
    (re.compile(r'^(LS|LSBUF|LSHIFT|LVLSHIFTER)$'), lambda m: "LS"),
    (re.compile(r'^(TIEHI|TIELO|TIE)$'), lambda m: "TIE"),
    (re.compile(r'^(FILL|FILLCELL|ENDCAP|ANT|ANTENNA|DECAP|TAP)$'), lambda m: "PHYS"),
    (re.compile(r'^(CKL[A-Z]+)$'), lambda m: "CLOCK_OTHER"),
    (re.compile(r'^(CLK[A-Z]+)$'), lambda m: "CLOCK_OTHER"),
]

KEYWORDS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'CLKINV'), "CLKINV"),
    (re.compile(r'CLKBUF|CKBD'), "CLKBUF"),
    (re.compile(r'CLKGATE|ICG'), "ICG"),
    (re.compile(r'MUX|MX[24]'), "MUX"),
    (re.compile(r'XNOR'), "XNOR"),
    (re.compile(r'XOR'), "XOR"),
    (re.compile(r'NAND'), "NAND"),
    (re.compile(r'NOR'), "NOR"),
    (re.compile(r'\bINV\b|INVD|INVX'), "INV"),
    (re.compile(r'BUFF|BUFX|BUF'), "BUF"),
    (re.compile(r'AOI'), "AOI"),
    (re.compile(r'OAI'), "OAI"),
    (re.compile(r'DFF'), "DFF"),
    (re.compile(r'LAT|LATCH|DLH|DLL|LHQ'), "LATCH"),
    (re.compile(r'ISO|ISOL'), "ISO"),
    (re.compile(r'LSBUF|LSHIFT|LVLSH'), "LS"),
    (re.compile(r'TIEHI|TIELO|TIE'), "TIE"),
    (re.compile(r'FILL|ENDCAP|ANT|DECAP|TAP'), "PHYS"),
]

CELLTYPE2ID = {
    "INV": 1, "BUF": 2, "NAND": 3, "NOR": 4,
    "XOR": 5, "XNOR": 6, "AOI": 7, "OAI": 8,
    "MUX": 9, "DFF": 10, "LATCH": 11, "CLKBUF": 12,
    "ICG": 13, "CLOCK_OTHER": 14, "ISO": 15, "LS": 16,
    "TIE": 17, "PHYS": 18, "OTHER": 19, "CLKINV": 20,
    # 你的模式里会命中 AND/OR，这里补上编号避免 KeyError
    "AND": 21, "OR": 22,
}

def infer_celltype(cellname: str) -> str:
    base_full = normalize_name(cellname)
    base, _ = strip_drive_digits(base_full)
    # 先前缀/整词匹配
    for rx, fn in PATTERNS:
        m = rx.match(base)
        if m:
            t = fn(m)
            return t if t in CELLTYPE2ID else "OTHER"
    # 再关键词扫描（包含在字符串内部）
    for rx, t in KEYWORDS:
        if rx.search(base_full):
            return t if t in CELLTYPE2ID else "OTHER"
    return "OTHER"

@dataclass
class CellClassifier:
    # 允许一组候选列名
    name_candidates: tuple = ("cellname","cell_name","cell","name","cell-master","master","macro","celltype")
    def find_name_col(self, df: pd.DataFrame) -> str:
        for c in df.columns:
            if c.lower() in self.name_candidates:
                return c
        raise ValueError(f"找不到 cellname 列。接受列名：{self.name_candidates}；当前列：{list(df.columns)}")

    def classify_df(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        col = self.find_name_col(df)
        df["celltype"] = df[col].map(infer_celltype)
        df["celltype_id"] = df["celltype"].map(CELLTYPE2ID).astype("int64")
        return df

def classify_raw_to_celltypes(raw_csv: str, out_csv: str) -> str:
    """供 prepare_data.run() 调用的无副作用函数。"""
    df = pd.read_csv(raw_csv)
    clf = CellClassifier()
    out = clf.classify_df(df)
    out.to_csv(out_csv, index=False)
    return out_csv
