"""Audit report: what determined the decision, which requirements it involves, and how well-evidenced it is."""
from __future__ import annotations

from .explain import Explanation
from .types import Case


def audit_report(case: Case, run, exp: Explanation, dialogue=None) -> str:
    st = dialogue.status_by_eid() if dialogue else {}
    L = [f"# Audit report — {case.case_id}", "",
         f"**Decision:** {exp.verdict}  (gold: {case.gold['decision']})  ",
         f"**Natural variability (baseline flip rate p0):** {exp.p0:.2f}  ",
         f"**Replays spent:** {exp.replays}  ",
         f"**Explanation sufficient (keep-only replay):** {exp.sufficient} (rate {exp.sufficiency_rate:.2f})", "",
         "## Decisive requirements (replay-verified)", "",
         "| requirement | criticality | statement | effect over baseline | 95% CI | perturbation | evidence |",
         "|---|---|---|---|---|---|---|"]
    for g in exp.groups:
        if g.key.startswith("R"):
            req = run.elements.get(f"req:{g.key}")
            stmt = f"{req.content['param']} {req.content['op']} {req.content['thr']:g} {req.content['unit']}" if req else "?"
            L.append(f"| {g.key} | {req.criticality if req else '?'} | {stmt} | +{g.effect:.2f} | "
                     f"[{g.ci[0]:.2f}, {g.ci[1]:.2f}] | {g.variant} | {st.get('req:' + g.key, '-')} / {st.get('ver:' + g.key, '-')} |")
        else:
            L.append(f"| {g.key} | - | decision policy | +{g.effect:.2f} | [{g.ci[0]:.2f}, {g.ci[1]:.2f}] | {g.variant} | - |")
    L += ["", "## Decisive information elements", ""]
    for e in exp.elements:
        L.append(f"- `{e.key}` ({run.elements[e.key].kind}, by {run.elements[e.key].agent}) — effect +{e.effect:.2f} via `{e.variant}`")
    cited = {j.split(':')[1] for j in run.justification}
    true = exp.group_ids
    L += ["", "## Faithfulness check of the agent's own textual justification", "",
          f"- cited by the decider: {sorted(cited)}", f"- replay-verified: {sorted(true)}",
          f"- **justification faithful:** {cited == true}"]
    if dialogue:
        from collections import Counter
        L += ["", "## Dialogue (claims checked outside the model)", "",
              f"- claim status: {dict(Counter(c.status for c in dialogue.claims.values()))}",
              f"- moves: {dialogue.n_moves}; protocol violations: {len(dialogue.violations)}"]
        for c in dialogue.claims.values():
            if c.status == "REFUTED":
                L.append(f"- ⚠ `{c.cid}` REFUTED: {c.failures}")
        suspects = sorted(true & dialogue.refuted_rids())
        L += ["", "## Audit flags", "",
              (f"- **Decisive AND refuted → prime suspects for the decision error:** {suspects}" if suspects
               else "- No decisive requirement has a refuted claim.")]
    return "\n".join(L) + "\n"
