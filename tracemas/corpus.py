"""Synthetic requirements-driven corpus generator with known ground truth.

Each case = a specification (requirements with criticality A/B/C), a design
datasheet (measured values) and a decision policy. Constraints are explicit, so
compliance and the origin of an error are objectively checkable (as in the
PhD's industrial use cases).
"""
from __future__ import annotations

import random

from .parsing import WORDS, evaluate
from .types import Case, Passage

PARAMS = [("operating pressure", "bar"), ("flow rate", "L/min"), ("coolant temperature", "°C"),
          ("response time", "ms"), ("vibration level", "mm/s"), ("noise level", "dB"),
          ("supply voltage", "V"), ("leakage rate", "mL/h"), ("efficiency", "%"),
          ("mass", "kg"), ("start-up delay", "s"), ("burst pressure", "bar"),
          ("housing stiffness", "kN/mm"), ("MTBF", "h"), ("power consumption", "W"),
          ("sampling frequency", "Hz")]
THRESHOLDS = [2, 5, 8, 10, 12, 15, 20, 25, 40, 50, 80, 100, 150, 200]
DEFAULT_POLICY = {"reject_on": ["A", "B"]}


def make_case(seed: int, n_req: int = 10, n_noise: int = 2, scenario: str | None = None) -> Case:
    rng = random.Random(seed)
    n_req = min(n_req, len(PARAMS))
    params = rng.sample(PARAMS, n_req)
    reqs = []
    for i, (param, unit) in enumerate(params, 1):
        crit = rng.choices("ABC", weights=[3, 4, 3])[0]
        if i == 1:
            crit = "A"
        if i == 2:
            crit = "B"
        reqs.append({"rid": f"R{i}", "param": param, "unit": unit, "crit": crit,
                     "op": rng.choice(["<=", ">="]), "thr": float(rng.choice(THRESHOLDS))})
    rng.shuffle(reqs)
    scenario = scenario or rng.choice(["accept", "reject"])
    critical = [r for r in reqs if r["crit"] in "AB"]
    failing = set()
    if scenario == "reject":
        failing |= {r["rid"] for r in rng.sample(critical, rng.choice([1, 1, 2]))}
    failing |= {r["rid"] for r in reqs if r["crit"] == "C" and rng.random() < 0.35}

    spec, design, values = [], [], {}
    for r in reqs:
        margin = rng.uniform(0.12, 0.45)
        bad = r["rid"] in failing
        up = (r["op"] == "<=") == bad          # fail&<= -> above ; pass&>= -> above
        val = round(r["thr"] * (1 + margin if up else 1 - margin), 2)
        values[r["rid"]] = val
        spec.append(Passage(r["rid"], f"[{r['rid']}] The {r['param']} shall be {WORDS[r['op']]} "
                                      f"{r['thr']:g} {r['unit']}. Criticality: {r['crit']}."))
        design.append(Passage(f"D-{r['rid']}", f"[D-{r['rid']}] Measured {r['param']}: {val:g} {r['unit']}."))
        assert evaluate(r["op"], val, r["thr"]) == (not bad)
    for j in range(n_noise):
        spec.insert(rng.randrange(len(spec) + 1),
                    Passage(f"N{j+1}", f"[N{j+1}] General note: this specification applies to hydraulic unit HU-{rng.randint(10, 99)}."))
    rng.shuffle(design)
    policy = dict(DEFAULT_POLICY)
    bad_ab = sorted(rid for rid in failing if next(r for r in reqs if r["rid"] == rid)["crit"] in policy["reject_on"])
    gold = {"decision": "REJECT" if bad_ab else "ACCEPT", "failing": sorted(failing),
            "failing_critical": bad_ab, "requirements": {r["rid"]: r for r in reqs}, "values": values}
    return Case(f"case-{seed}", spec, design, policy, gold)
