"""Command line: `python -m tracemas demo|benchmark|generate`."""
from __future__ import annotations

import argparse
import json
import os

from .bench import run_all, save, make_injection
from .corpus import make_case
from .dialogue import SimProponent, run_dialogue
from .explain import Config, PerturbationExplainer
from .llm import NoiseConfig, SimulatedLLM
from .pipeline import Pipeline
from .provenance import to_dot, to_prov_json
from .report import audit_report


def _llm(args):
    if getattr(args, "backend", "sim") == "anthropic":
        from .llm import AnthropicLLM
        return AnthropicLLM()
    return SimulatedLLM(NoiseConfig().scaled(args.noise))


def demo(args):
    import random
    case = make_case(args.seed, args.n_req)
    pipe = Pipeline(_llm(args))
    fixed = None
    if args.inject:
        inj = make_injection(case, Pipeline(SimulatedLLM(NoiseConfig.zero())), random.Random(args.seed))
        if inj:
            fixed = inj[0]
            print(f"[inject] hallucinated requirement injected at {list(fixed)[0]} (gold decision: {case.gold['decision']})")
    run = pipe.run(case, args.seed, fixed)
    exp = PerturbationExplainer(pipe, Config(), fixed, seed0=args.seed * 100_000).explain(case)
    dlg = run_dialogue(case, run, SimProponent(case, 0.1, args.seed))
    os.makedirs(args.out, exist_ok=True)
    md = audit_report(case, run, exp, dlg)
    open(f"{args.out}/audit_report.md", "w").write(md)
    open(f"{args.out}/case.json", "w").write(json.dumps(case.to_dict(), indent=2))
    open(f"{args.out}/provenance.json", "w").write(json.dumps(to_prov_json(run, dlg.status_by_eid()), indent=2, default=str))
    open(f"{args.out}/provenance.dot", "w").write(to_dot(run, exp.element_ids, dlg.status_by_eid()))
    print(md)
    print(f"files written to {args.out}/ (render the graph: dot -Tpng provenance.dot -o provenance.png)")


def bench(args):
    res = run_all(quick=args.quick)
    save(res, args.out)
    print(open(f"{args.out}/results.md").read())


def generate(args):
    print(json.dumps(make_case(args.seed, args.n_req).to_dict(), indent=2))


def main(argv=None):
    ap = argparse.ArgumentParser("tracemas", description="Replay-verified explanations for multi-agent chains")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="run chain + explanation + dialogue + audit report on one case")
    d.add_argument("--seed", type=int, default=7); d.add_argument("--n-req", type=int, default=10)
    d.add_argument("--noise", type=float, default=1.0); d.add_argument("--inject", action="store_true")
    d.add_argument("--backend", choices=["sim", "anthropic"], default="sim"); d.add_argument("--out", default="out")
    d.set_defaults(fn=demo)
    b = sub.add_parser("benchmark", help="run experiments E1-E4")
    b.add_argument("--quick", action="store_true"); b.add_argument("--out", default="results")
    b.set_defaults(fn=bench)
    g = sub.add_parser("generate", help="print a synthetic case as JSON")
    g.add_argument("--seed", type=int, default=0); g.add_argument("--n-req", type=int, default=10)
    g.set_defaults(fn=generate)
    args = ap.parse_args(argv)
    args.fn(args)
