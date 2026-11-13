"""Hierarchical evaluation (faithfulness -> coverage/diagnosis -> cost), as in the PhD protocol.

E1  Faithfulness vs ground truth  : explanation = true decisive requirements? (precision / recall / F1, replays)
E2  Injected-error localisation   : a known error is injected; do methods point at it? (hit-rate, explanation size)
E3  Variability study             : natural run-to-run variability vs noise level; effect on faithfulness
E4  Dialogue verification         : refutation of hallucinated extractions; moves spent per criticality
Baselines: textual justification (as produced by the agent), provenance ancestors (all upstream), flat replay.
"""
from __future__ import annotations

import json
import random
import statistics as st
from collections import Counter, defaultdict

from .corpus import make_case
from .dialogue import SimProponent, run_dialogue
from .explain import Config, PerturbationExplainer, oracle_explanation
from .llm import NoiseConfig, SimulatedLLM
from .parsing import parse_spec, rid_of
from .pipeline import Pipeline
from .types import Intervention


def prf(pred: set, truth: set):
    tp = len(pred & truth)
    p = tp / len(pred) if pred else (1.0 if not truth else 0.0)
    r = tp / len(truth) if truth else 1.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def _rids(eids) -> set:
    return {e.split(":")[1] for e in eids if e.split(":")[1].startswith("R")}


def methods(noise: NoiseConfig, cfg: Config | None = None):
    cfg = cfg or Config()
    return {
        "text_justification": None, "provenance_ancestors": None,
        "replay_flat": (cfg_with(cfg, crit_aware=False, early_stop=False), False),
        "replay_hier_uniform": (cfg_with(cfg, crit_aware=False), True),
        "replay_hier_crit": (cfg_with(cfg), True),
    }


def cfg_with(cfg: Config, **kw) -> Config:
    return Config(**{**cfg.__dict__, **kw})


def predict(name, spec, case, noise, seed, fixed=None):
    """Return (predicted requirement-groups, replays) for one method on one case."""
    pipe = Pipeline(SimulatedLLM(noise))
    if name == "text_justification":
        run = pipe.run(case, seed, fixed)
        return _rids(run.justification), 1
    if name == "provenance_ancestors":
        run = pipe.run(case, seed, fixed)
        return {g for g in run.groups(run.ancestors("dec:final")) if g.startswith("R")}, 1
    cfg, hier = spec
    exp = PerturbationExplainer(pipe, cfg, fixed, seed0=seed * 100_000).explain(case, hierarchical=hier)
    return exp.group_ids, exp.replays


def e1_faithfulness(n_cases=24, noise=None, seed0=0, n_req=10, cfg=None):
    noise = noise or NoiseConfig()
    oracle_pipe = Pipeline(SimulatedLLM(NoiseConfig.zero()))
    agg = defaultdict(lambda: defaultdict(list))
    for s in range(seed0, seed0 + n_cases):
        case = make_case(s, n_req)
        _, truth, _ = oracle_explanation(oracle_pipe, case)
        for name, spec in methods(noise, cfg).items():
            pred, rep = predict(name, spec, case, noise, s + 1)
            p, r, f = prf(pred, truth)
            a = agg[name]
            a["p"].append(p); a["r"].append(r); a["f1"].append(f)
            a["exact"].append(float(pred == truth)); a["replays"].append(rep)
            a["size"].append(len(pred)); a[f"f1_{case.gold['decision']}"].append(f)
    return {n: {k: round(st.mean(v), 3) for k, v in d.items()} for n, d in agg.items()}


def make_injection(case, noise_free: Pipeline, rng: random.Random):
    """Inject a hallucinated requirement that flips the decision. Returns (interventions, rid) or None."""
    ref = noise_free.run(case, 0)
    gold = case.gold["decision"]
    if gold == "ACCEPT":
        rid = rng.choice([r for r, e in ((e.req_id, e) for e in ref.elements.values() if e.kind == "req")
                          if e.criticality in "AB"])
        c = dict(ref.elements[f"req:{rid}"].content); c["op"] = ">=" if c["op"] == "<=" else "<="   # inverted comparison
    else:
        if len(case.gold["failing_critical"]) != 1:
            return None
        rid = case.gold["failing_critical"][0]
        c = dict(ref.elements[f"req:{rid}"].content)
        v = case.gold["values"][rid]
        c["thr"] = round(v * (1.3 if c["op"] == "<=" else 0.7), 2)                                   # relaxed threshold
    ivs = {f"req:{rid}": Intervention("inject", value=c)}
    wrong = noise_free.run(case, 0, ivs).verdict
    return (ivs, rid) if wrong != gold else None


def e2_injection(n_cases=40, noise=None, seed0=500, cfg=None):
    noise = noise or NoiseConfig()
    nf = Pipeline(SimulatedLLM(NoiseConfig.zero()))
    rng = random.Random(1)
    res = defaultdict(lambda: defaultdict(list))
    n_used, s = 0, seed0
    while n_used < n_cases and s < seed0 + 10 * n_cases:
        case = make_case(s); s += 1
        inj = make_injection(case, nf, rng)
        if not inj:
            continue
        ivs, rid = inj
        pipe = Pipeline(SimulatedLLM(noise))
        if pipe.run(case, s, ivs).verdict == case.gold["decision"]:
            continue                                   # noise cancelled the error: not a wrong decision
        n_used += 1
        for name, spec in methods(noise, cfg).items():
            pred, rep = predict(name, spec, case, noise, s, ivs)
            a = res[name]
            a["hit"].append(float(rid in pred)); a["size"].append(len(pred))
            a["precision_if_hit"].append(1 / len(pred) if rid in pred and pred else 0.0)
            a["replays"].append(rep)
        # dialogue-based detection (cheap structural check; not a faithfulness proof)
        run = pipe.run(case, s, ivs)
        d = run_dialogue(case, run, SimProponent(case, 0.1, s))
        a = res["dialogue_refutation"]
        a["hit"].append(float(rid in d.refuted_rids())); a["size"].append(len(d.refuted_rids()))
        a["precision_if_hit"].append(1 / len(d.refuted_rids()) if rid in d.refuted_rids() else 0.0)
        a["replays"].append(0)
    out = {n: {k: round(st.mean(v), 3) for k, v in d.items()} for n, d in res.items()}
    out["_n_cases"] = n_used
    return out


def e3_variability(scales=(0.0, 0.5, 1.0, 2.0, 3.0), n_cases=12, seed0=900):
    out = {}
    for sc in scales:
        noise = NoiseConfig().scaled(sc)
        oracle_pipe = Pipeline(SimulatedLLM(NoiseConfig.zero()))
        p0s, f1s, reps = [], [], []
        for s in range(seed0, seed0 + n_cases):
            case = make_case(s)
            _, truth, _ = oracle_explanation(oracle_pipe, case)
            exp = PerturbationExplainer(Pipeline(SimulatedLLM(noise)), Config(), seed0=s * 100_000).explain(case)
            p0s.append(exp.p0); f1s.append(prf(exp.group_ids, truth)[2]); reps.append(exp.replays)
        out[str(sc)] = {"natural_flip_rate_p0": round(st.mean(p0s), 3), "f1": round(st.mean(f1s), 3),
                        "replays": round(st.mean(reps), 1)}
    return out


def e4_dialogue(n_cases=30, noise=None, seed0=1300, p_fab=0.1):
    noise = noise or NoiseConfig().scaled(2.0)
    tp = fp = fn = 0
    by = defaultdict(lambda: [0, 0])      # crit -> [errors caught, errors total]
    moves = defaultdict(list)
    viol = 0
    for s in range(seed0, seed0 + n_cases):
        case = make_case(s)
        run = Pipeline(SimulatedLLM(noise)).run(case, s)
        d = run_dialogue(case, run, SimProponent(case, p_fab, s))
        viol += len(d.violations)
        for cid, c in d.claims.items():
            if c.scheme == "extraction_from_source":
                wrong = c.content != parse_spec(next(p.text for p in case.spec if p.pid == c.refs["passage"]))
                moves[c.crit].append(sum(1 for m in d.transcript if m.claim_id == cid))
                tp += wrong and c.status == "REFUTED"; fp += (not wrong) and c.status == "REFUTED"
                fn += wrong and c.status != "REFUTED"
                if wrong:
                    by[c.crit][1] += 1; by[c.crit][0] += c.status == "REFUTED"
    # recall is expected to be < 1 for C-level claims (burden of proof deliberately minimal)
    return {"extraction_errors_refuted": tp, "false_refutations": fp, "missed_errors": fn,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None,
            "recall_by_criticality": {k: (round(v[0] / v[1], 2) if v[1] else None) for k, v in sorted(by.items())},
            "moves_per_claim_by_criticality": {k: round(st.mean(v), 2) for k, v in sorted(moves.items())},
            "protocol_violations": viol}


def run_all(quick=False) -> dict:
    n = (6, 10, 4, 8) if quick else (24, 40, 12, 30)
    return {"E1_faithfulness": e1_faithfulness(n[0]), "E2_injection": e2_injection(n[1]),
            "E3_variability": e3_variability(n_cases=n[2]), "E4_dialogue": e4_dialogue(n[3]),
            "note": "Simulated agents with controllable noise; see README for scope and limits."}


def to_markdown(r: dict) -> str:
    L = ["# TRACE-MAS benchmark results (simulated agents)\n"]
    L += ["## E1 — Faithfulness vs noise-free ground truth (requirement-level)\n",
          "| method | precision | recall | F1 | exact | avg #groups | avg replays |", "|---|---|---|---|---|---|---|"]
    for m, v in r["E1_faithfulness"].items():
        L.append(f"| {m} | {v['p']} | {v['r']} | {v['f1']} | {v['exact']} | {v['size']} | {v['replays']} |")
    e2 = r["E2_injection"]
    L += [f"\n## E2 — Localising an injected (hallucinated) requirement ({e2['_n_cases']} wrong decisions)\n",
          "| method | hit-rate | avg #groups flagged | precision if hit | avg replays |", "|---|---|---|---|---|"]
    for m, v in e2.items():
        if m != "_n_cases":
            L.append(f"| {m} | {v['hit']} | {v['size']} | {v['precision_if_hit']} | {v['replays']} |")
    L += ["\n## E3 — Natural variability vs noise level\n", "| noise ×| natural flip rate p0 | F1 (replay_hier_crit) | replays |", "|---|---|---|---|"]
    for k, v in r["E3_variability"].items():
        L.append(f"| {k} | {v['natural_flip_rate_p0']} | {v['f1']} | {v['replays']} |")
    d = r["E4_dialogue"]
    L += ["\n## E4 — Dialogue protocol (burden of proof ∝ criticality)\n",
          f"- extraction errors refuted: {d['extraction_errors_refuted']}, missed: {d['missed_errors']}, "
          f"false refutations: {d['false_refutations']}, recall: {d['recall']}",
          f"- recall by criticality (errors in C-claims are deliberately unchallenged): {d['recall_by_criticality']}",
          f"- moves per claim by criticality: {d['moves_per_claim_by_criticality']}",
          f"- protocol violations found by external conformity check: {d['protocol_violations']}"]
    return "\n".join(L) + "\n"


def save(results: dict, outdir: str):
    import os
    os.makedirs(outdir, exist_ok=True)
    json.dump(results, open(f"{outdir}/results.json", "w"), indent=2)
    open(f"{outdir}/results.md", "w").write(to_markdown(results))
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        e1 = results["E1_faithfulness"]; names = list(e1)
        fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
        ax[0].bar(names, [e1[n]["f1"] for n in names], color="#4C72B0"); ax[0].set_title("E1: F1 vs ground truth"); ax[0].set_ylim(0, 1)
        ax[1].bar(names, [e1[n]["replays"] for n in names], color="#DD8452"); ax[1].set_title("E1: replays per decision")
        for a in ax:
            a.tick_params(axis="x", rotation=30)
            for l in a.get_xticklabels(): l.set_ha("right")
        fig.tight_layout(); fig.savefig(f"{outdir}/e1.png", dpi=140)
    except Exception:
        pass
