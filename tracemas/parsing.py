"""Deterministic parsers/evaluators (the 'outside the model' ground truth)."""
from __future__ import annotations

import re
from typing import Optional

SPEC_RE = re.compile(
    r"\[(?P<rid>R\d+)\] The (?P<param>.+?) shall be (?P<op>at most|at least) "
    r"(?P<thr>-?\d+(?:\.\d+)?) (?P<unit>\S+?)\. Criticality: (?P<crit>[ABC])\.")
DESIGN_RE = re.compile(
    r"\[D-(?P<rid>R\d+)\] Measured (?P<param>.+?): (?P<val>-?\d+(?:\.\d+)?) (?P<unit>\S+?)\.?$")
OPS = {"at most": "<=", "at least": ">="}
WORDS = {v: k for k, v in OPS.items()}


def parse_spec(text: str) -> Optional[dict]:
    m = SPEC_RE.search(text)
    if not m:
        return None
    return {"rid": m["rid"], "param": m["param"], "op": OPS[m["op"]],
            "thr": float(m["thr"]), "unit": m["unit"], "crit": m["crit"]}


def parse_design(text: str) -> Optional[dict]:
    m = DESIGN_RE.search(text.strip())
    if not m:
        return None
    return {"rid": m["rid"], "param": m["param"], "value": float(m["val"]), "unit": m["unit"]}


def evaluate(op: str, value: float, thr: float) -> bool:
    return value <= thr if op == "<=" else value >= thr


def rid_of(pid: str) -> Optional[str]:
    if re.fullmatch(r"R\d+", pid):
        return pid
    if re.fullmatch(r"D-R\d+", pid):
        return pid[2:]
    return None
