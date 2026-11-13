"""Requirements-driven multi-agent chain with built-in provenance capture.

Chain:  Extractor (spec -> requirement) -> Reader (datasheet -> value)
        -> Verifier (requirement x value -> pass/fail) -> Decider (policy -> verdict)

Every information element gets a *stable* id (``src:R3``, ``req:R3``, ``ver:R3`` ...)
so that executions can be replayed under do()-style interventions and compared.
"""
from __future__ import annotations

import copy
import re

from .parsing import parse_design, rid_of
from .types import Case, Element, Intervention

SCALE = {"scale_up": 1.6, "scale_down": 0.4}
VARIANTS = {"spec": ["flip_op"], "design": ["scale_up", "scale_down"], "req": ["flip_op"],
            "val": ["scale_up", "scale_down"], "ver": ["flip_result"], "policy": ["relax"]}


def mutate(kind: str, content, variant: str):
    """Type-specific counterfactual alteration of an element."""
    if kind == "spec" and variant == "flip_op":
        return content.replace("at most", "@@").replace("at least", "at most").replace("@@", "at least")
    if kind == "design":
        f = SCALE[variant]
        return re.sub(r": (-?\d+(?:\.\d+)?) ", lambda m: f": {float(m.group(1)) * f:g} ", content, count=1)
    if kind == "req" and variant == "flip_op":
        c = dict(content); c["op"] = ">=" if c["op"] == "<=" else "<="; return c
    if kind == "val":
        return {"value": round(content["value"] * SCALE[variant], 4)}
    if kind == "ver" and variant == "flip_result":
        return {"result": "fail" if content["result"] == "pass" else "pass"}
    if kind == "policy" and variant == "relax":
        return {"reject_on": []}
    raise ValueError(f"no mutation {variant!r} for kind {kind!r}")


class Run:
    """One execution: elements (with `used` edges = the provenance DAG) + verdict."""

    def __init__(self, case_id: str, seed: int):
        self.case_id, self.seed = case_id, seed
        self.elements: dict[str, Element] = {}
        self.removed: set[str] = set()
        self.verdict: str | None = None
        self.justification: list[str] = []

    def ancestors(self, eid: str) -> set[str]:
        seen, stack = set(), [eid]
        while stack:
            for u in self.elements[stack.pop()].used:
                if u not in seen:
                    seen.add(u); stack.append(u)
        return seen

    def groups(self, eids) -> dict:
        """Group elements by requirement id (policy gets its own group)."""
        out: dict = {}
        for e in eids:
            el = self.elements[e]
            key = el.req_id if el.req_id else ("__policy__" if el.kind == "policy" else None)
            if key:
                out.setdefault(key, []).append(e)
        return out

    def group_criticality(self, rid: str) -> str:
        req = self.elements.get(f"req:{rid}")
        return req.criticality if req and req.criticality else "A"


class Pipeline:
    def __init__(self, llm):
        self.llm = llm

    def run(self, case: Case, seed: int = 0, interventions: dict | None = None) -> Run:
        iv: dict[str, Intervention] = interventions or {}
        run = Run(case.case_id, seed)

        def produce(eid, kind, agent, task, used, compute, req_id=None):
            used = tuple(u for u in used if u in run.elements)
            spec = iv.get(eid)
            if spec and spec.op == "revert":      # undo a persistent (injected) error: recompute honestly
                spec = None
            if spec and spec.op == "remove":
                run.removed.add(eid); return None
            if spec and spec.op == "inject":
                content = copy.deepcopy(spec.value)
            else:
                content = compute()
                if content is None:
                    return None
                if spec and spec.op == "alter":
                    content = mutate(kind, content, spec.variant)
            el = Element(eid, kind, content, agent, task, used, req_id,
                         content.get("crit") if kind == "req" and isinstance(content, dict) else None,
                         perturbed=(spec.op + (":" + spec.variant if spec.variant else "")) if spec else None)
            run.elements[eid] = el
            return el

        for p in case.spec:
            produce(f"src:{p.pid}", "spec", "input", "read", (), lambda t=p.text: t, rid_of(p.pid))
        for p in case.design:
            produce(f"des:{rid_of(p.pid)}", "design", "input", "read", (), lambda t=p.text: t, rid_of(p.pid))
        produce("pol", "policy", "input", "read", (), lambda: dict(case.policy))

        for p in case.spec:                                   # agent 1: Extractor
            s = run.elements.get(f"src:{p.pid}")
            if not s:
                continue
            eid = f"req:{p.pid}"
            produce(eid, "req", "extractor", "extract", (s.eid,),
                    lambda s=s, eid=eid: self.llm.complete("extract", {"text": s.content}, eid, seed), rid_of(p.pid))
        reqs = {e.req_id: e for e in run.elements.values() if e.kind == "req"}

        for rid in reqs:                                      # agent 2: Reader
            d = run.elements.get(f"des:{rid}")
            if d:
                produce(f"val:{rid}", "val", "reader", "read_value", (d.eid,),
                        lambda d=d, rid=rid: self.llm.complete("read_value", {"text": d.content}, f"val:{rid}", seed), rid)

        for rid, req in reqs.items():                         # agent 3: Verifier
            val = run.elements.get(f"val:{rid}")

            def compute(req=req, val=val, rid=rid):
                if val is None:
                    return {"result": "missing"}
                return self.llm.complete("verify", {"req": req.content, "value": val.content["value"]}, f"ver:{rid}", seed)
            produce(f"ver:{rid}", "ver", "verifier", "verify",
                    tuple(x.eid for x in (req, val) if x), compute, rid)

        vers = {e.req_id: e for e in run.elements.values() if e.kind == "ver"}   # agent 4: Decider
        pol = run.elements.get("pol")
        payload = {"verifications": {r: {"result": v.content["result"], "crit": reqs[r].criticality or "A"}
                                     for r, v in vers.items()},
                   "policy": pol.content if pol else None}
        dec = produce("dec:final", "decision", "decider", "decide",
                      tuple(v.eid for v in vers.values()) + (("pol",) if pol else ()),
                      lambda: self.llm.complete("decide", payload, "dec:final", seed))
        run.verdict = dec.content["verdict"]
        run.justification = [f"{k}:{r}" for r in dec.content["cited_rids"] for k in ("req", "ver")]
        return run
