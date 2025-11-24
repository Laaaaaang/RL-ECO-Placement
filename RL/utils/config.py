from __future__ import annotations
from types import SimpleNamespace
import yaml

def load_cfg(path: str) -> SimpleNamespace:
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    # flatten first-level keys to namespaces
    ns = SimpleNamespace(**data)
    # also nest common subsections if dict
    for k, v in data.items():
        if isinstance(v, dict):
            setattr(ns, k, SimpleNamespace(**v))
    return ns
