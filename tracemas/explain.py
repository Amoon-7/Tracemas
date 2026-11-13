"""Replay-verified explanations (RQ1, RQ2).

An explanation = the set of information elements whose controlled perturbation
(removal / counterfactual alteration) changes the decision *beyond the system's
natural run-to-run variability*, linked to the requirements they belong to.

Cost control (the methodological challenge):
  * the provenance graph restricts candidates to ancestors of the decision;
  * grouped ablation: test whole requirement-groups first, drill down only into
    decisive groups (hierarchical, delta-debugging flavour);
  * evidence budget proportional to requirement criticality (RQ3);
  * sequential early stopping inside each test.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from .pipeline import VARIANTS, Pipeline, Run
from .stats import fisher_one_sided, wilson
from .types import CRIT_WEIGHT, Case, Intervention

POLICY_GROUP = "__policy__"


@dataclass
class Config:
    k_baseline: int = 16        # replays used to measure natural variability
    n_min: int = 6              # replays for the least critical requirements (C)
    n_max: int = 14             # replays for the most critical requirements (A)
    alpha: float = 0.05
    min_effect: float = 0.4     # required flip-rate excess over baseline
    crit_aware: bool = True
    early_stop: bool = True
    batch: int = 2
    sufficiency_n: int = 10


@dataclass
class Scored:
    key: str                    # element id or group id
    effect: float
    rate: float
    p: float
    variant: str
    n: int
    ci: tuple = (0.0, 1.0)


@dataclass
class Explanation:
    method: str
    verdict: str
    p0: float                                   # natural flip rate (variability)
    groups: list = field(default_factory=list)    # decisive requirement groups (Scored)
    elements: list = field(default_factory=list)  # decisive elements (Scored)
    tested_groups: int = 0
    tested_elements: int = 0
    replays: int = 0
    sufficient: bool | None = None
    sufficiency_rate: float | None = None

    @property
    def group_ids(self) -> set:
        return {g.key for g in self.groups if g.key != POLICY_GROUP}

    @property
    def element_ids(self) -> set:
        return {e.key for e in self.elements}


class PerturbationExplainer:
    def __init__(self, pipeline: Pipeline, cfg: Config | None = None, fixed: dict | None = None, seed0: int = 10_000):
        self.pipe, self.cfg, self.fixed, self._seed = pipeline, cfg or Config(), dict(fixed or {}), seed0
        self.replays = 0

    # ---- replay machinery -------------------------------------------------
    def _next_seed(self) -> int:
        self._seed += 1
        return self._seed

    def _replay(self, case: Case, ivs: dict) -> str:
        self.replays += 1
        return self.pipe.run(case, self._next_seed(), {**self.fixed, **ivs}).verdict

    def baseline(self, case: Case):
        runs = [self.pipe.run(case, self._next_seed(), self.fixed) for _ in range(self.cfg.k_baseline)]
        self.replays += len(runs)
        verdicts = Counter(r.verdict for r in runs)
        d0 = verdicts.most_common(1)[0][0]
        ref = next(r for r in runs if r.verdict == d0)
        f0 = sum(v for k, v in verdicts.items() if k != d0)
        return d0, ref, f0, len(runs)

    def _n_for(self, crit: str) -> int:
        c = self.cfg
        if not c.crit_aware:
            return c.n_max
        return round(c.n_min + (c.n_max - c.n_min) * CRIT_WEIGHT.get(crit, 1.0))

    def _significant(self, f, n, base) -> tuple[bool, float]:
        f0, k = base
        p = fisher_one_sided(f, n, f0, k)
        return (f / n - f0 / k >= self.cfg.min_effect and p < self.cfg.alpha), p

    def _test(self, case, ivs, n, success, base) -> tuple[int, int, bool, float]:
        """Sequential perturbation test. `success(verdict)` marks a replay as 'supporting'.
        Returns (supporting replays, replays used, significant?, p-value)."""
        f = m = 0
        step = self.cfg.batch if self.cfg.early_stop else n
        while m < n:
            for _ in range(min(step, n - m)):
                f += bool(success(self._replay(case, ivs)))
                m += 1
            if self.cfg.early_stop and m >= 4:
                sig, p = self._significant(f, m, base)
                if f == 0 or (sig and f / m >= 0.9):
                    return f, m, sig, p
        sig, p = self._significant(f, m, base)
        return f, m, sig, p

    # ---- perturbation catalogue ------------------------------------------
    @staticmethod
    def _group_ivs(run: Run, key: str, variant: str, fixed: dict | None = None) -> dict:
        if variant == "revert":     # undo the persistent errors (injected/known) inside the group
            return {e: Intervention("revert") for e in (fixed or {}) if run.elements.get(e) and run.elements[e].req_id == key}
        if key == POLICY_GROUP:
            return {"pol": Intervention("remove")} if variant == "remove" else {"pol": Intervention("alter", "relax")}
        if variant == "remove":
            return {e: Intervention("remove") for e, el in run.elements.items()
                    if el.req_id == key and el.kind != "decision"}
        return {f"ver:{key}": Intervention("alter", "flip_result")}

    @staticmethod
    def _element_ivs(run: Run, eid: str, fixed: dict | None = None):
        kind = run.elements[eid].kind
        yield "remove", {eid: Intervention("remove")}
        if eid in (fixed or {}):
            yield "revert", {eid: Intervention("revert")}
        for v in VARIANTS.get(kind, []):
            yield v, {eid: Intervention("alter", v)}

    def _score(self, key, best, base, n_tot) -> Scored:
        f, n, p, variant = best
        return Scored(key, f / n - base[0] / base[1], f / n, p, variant, n_tot, wilson(f, n))

    @staticmethod
    def keep_only(ref: Run, keep) -> dict:
        """Context: remove every requirement group except those in `keep` (held contingency)."""
        ivs: dict = {}
        for g in ref.groups(ref.ancestors("dec:final")):
            if g != POLICY_GROUP and g not in keep:
                ivs.update(PerturbationExplainer._group_ivs(ref, g, "remove"))
        return ivs

    def _group_variants(self, members) -> tuple:
        return ("remove", "flip") + (("revert",) if any(m in self.fixed for m in members) else ())

    def _necessity(self, case, ivs_by_variant, n, d0, base):
        best = None
        for variant, ivs in ivs_by_variant:
            f, m, sig, p = self._test(case, ivs, n, lambda v: v != d0, base)
            if sig and (best is None or f / m > best[0] / best[1]):
                best = (f, m, p, variant)
        return best

    # ---- methods ----------------------------------------------------------
    def explain(self, case: Case, hierarchical: bool = True, name: str | None = None) -> Explanation:
        start = self.replays
        d0, ref, f0, k = self.baseline(case)
        base, p0 = (f0, k), f0 / k
        exp = Explanation(name or ("hier" if hierarchical else "flat"), d0, p0)
        anc = ref.ancestors("dec:final")
        groups = ref.groups(anc)
        context: dict[str, dict] = {}      # group -> context used for drill-down
        scored: dict[str, Scored] = {}

        # (1) necessity: does removing / flipping the group change the decision?
        if hierarchical:
            for key in sorted(groups):
                crit = "A" if key == POLICY_GROUP else ref.group_criticality(key)
                best = self._necessity(case, [(v, self._group_ivs(ref, key, v, self.fixed)) for v in self._group_variants(groups[key])],
                                       self._n_for(crit), d0, base)
                exp.tested_groups += 1
                if best:
                    scored[key] = self._score(key, best, base, self._n_for(crit)); context[key] = {}

            # (2) redundancy-aware sufficiency: a group that alone keeps the decision
            #     although emptiness would not (overdetermined REJECT decisions).
            n_e = max(6, self.cfg.sufficiency_n)
            empty = self.keep_only(ref, set())
            c0 = sum(self._replay(case, empty) == d0 for _ in range(n_e))
            if c0 / n_e <= 1 - self.cfg.min_effect:       # emptiness changes the verdict
                for key in sorted(groups):
                    if key in scored or key == POLICY_GROUP:
                        continue
                    n = self._n_for(ref.group_criticality(key))
                    ctx = self.keep_only(ref, {key})
                    f, m, sig, p = self._test(case, ctx, n, lambda v: v == d0, (c0, n_e))
                    exp.tested_groups += 1
                    if sig:
                        scored[key] = self._score(key, (f, m, p, "keep_only"), (c0, n_e), n)
                        context[key] = ctx
            exp.groups = sorted(scored.values(), key=lambda s: -s.effect)
            drill = [(e, context[g]) for g in scored for e in groups[g]]
        else:
            drill = [(e, {}) for e in sorted(anc)]

        # (3) element-level drill-down inside decisive groups (under their contexts)
        for eid, ctx in drill:
            el = ref.elements[eid]
            crit = "A" if (el.req_id is None) else ref.group_criticality(el.req_id)
            n = self._n_for(crit)
            best = self._necessity(case, [(v, {**ctx, **ivs}) for v, ivs in self._element_ivs(ref, eid, self.fixed)], n, d0, base)
            exp.tested_elements += 1
            if best:
                exp.elements.append(self._score(eid, best, base, n))
                if not hierarchical:
                    g = el.req_id or (POLICY_GROUP if el.kind == "policy" else None)
                    if g and g not in scored:
                        scored[g] = self._score(g, best, base, n)
        if not hierarchical:
            exp.groups = sorted(scored.values(), key=lambda s: -s.effect)
        exp.elements = sorted({e.key: e for e in exp.elements}.values(), key=lambda s: -s.effect)
        self._sufficiency(case, exp, ref, d0, base)
        exp.replays = self.replays - start
        return exp

    def _sufficiency(self, case, exp, ref, d0, base):
        """Keep only the explanation: removing every other requirement should preserve the decision
        about as often as an unperturbed replay does."""
        ivs = self.keep_only(ref, exp.group_ids)
        n = self.cfg.sufficiency_n
        same = sum(self._replay(case, ivs) == d0 for _ in range(n))
        exp.sufficiency_rate = same / n
        exp.sufficient = same / n >= (1 - base[0] / base[1]) - 0.15


def oracle_explanation(pipeline: Pipeline, case: Case, fixed: dict | None = None):
    """Noise-free exhaustive perturbation = ground-truth decisive set (necessity OR sole-sufficiency)."""
    fixed = fixed or {}
    ref = pipeline.run(case, 0, fixed)
    d0 = ref.verdict
    anc = ref.ancestors("dec:final")
    groups = ref.groups(anc)
    empty_changes = pipeline.run(case, 0, {**fixed, **PerturbationExplainer.keep_only(ref, set())}).verdict != d0
    els, grps = set(), set()
    for g, members in groups.items():
        ctx = {}
        if g != POLICY_GROUP:
            necessary = any(pipeline.run(case, 0, {**fixed, **PerturbationExplainer._group_ivs(ref, g, v, fixed)}).verdict != d0
                            for v in ("remove", "flip") + (("revert",) if any(m in fixed for m in members) else ()))
            alone = empty_changes and pipeline.run(case, 0, {**fixed, **PerturbationExplainer.keep_only(ref, {g})}).verdict == d0
            if not (necessary or alone):
                continue
            ctx = {} if necessary else PerturbationExplainer.keep_only(ref, {g})
            grps.add(g)
        for eid in members:
            for _, ivs in PerturbationExplainer._element_ivs(ref, eid, fixed):
                if pipeline.run(case, 0, {**fixed, **ctx, **ivs}).verdict != d0:
                    els.add(eid)
    return els, grps, ref
