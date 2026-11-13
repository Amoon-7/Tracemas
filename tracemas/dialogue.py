"""Protocol-imposed dialogue between agents (second direction, RQ3).

A protocol cannot be *expected* from an LLM -- it is *imposed* on it:
  * the orchestrator (``DialogueEngine``) fixes the admissible moves (dialogue-game
    tradition: Walton & Krabbe 1995) and rejects anything else;
  * claims instantiate *argument schemes* whose *critical questions* (Walton et al. 2008)
    define what the claimant is committed to;
  * every answer to a critical question is checked by a deterministic checker OUTSIDE the model;
  * the burden of proof is proportionate to requirement criticality (A > B > C).

The dialogue is NOT a proof of faithfulness: it yields structured, checked claims
(commitment store) that are then linked to the provenance graph and complement
replay-based verification.
"""
from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .parsing import WORDS, evaluate, parse_design, parse_spec
from .types import Case

TERMINAL = {"VERIFIED", "UNCHALLENGED", "REFUTED", "RETRACTED", "UNSUPPORTED"}


class Inadmissible(Exception):
    pass


@dataclass
class Move:
    kind: str                 # CLAIM | WHY | GROUND | RETRACT | CLOSE
    speaker: str              # proponent | challenger | orchestrator
    claim_id: str
    cq: Optional[str] = None
    payload: Any = None


@dataclass
class Claim:
    cid: str
    scheme: str
    content: dict
    refs: dict
    crit: str
    eid: str                  # provenance element the claim is about
    status: str = "OPEN"
    pending: Optional[str] = None
    satisfied: list = field(default_factory=list)
    failures: list = field(default_factory=list)
    quote: Optional[str] = None     # evidence committed at first GROUND (commitment store)


# ---- critical-question checkers (deterministic, outside the model) -----------------
def _passage(case: Case, pid: str) -> str:
    return next(p.text for p in case.spec + case.design if p.pid == pid)


def cq_quote_grounded(case, claim, ev):
    q = (ev or {}).get("quote", "")
    ok = bool(q.strip()) and q in _passage(case, claim.refs["passage"])
    return ok, "quote found verbatim in source" if ok else "quote NOT found in source passage"


def cq_value_fidelity(case, claim, ev):
    q = (ev or {}).get("quote", "")
    d = parse_spec(q)
    c = claim.content
    ok = q in _passage(case, claim.refs["passage"]) and bool(d) and d["op"] == c["op"] and d["thr"] == c["thr"] and d["unit"] == c["unit"] and d["crit"] == c["crit"]
    return ok, "claimed fields match the quote" if ok else f"claimed ({c['op']} {c['thr']}) != quote ({d and (d['op'], d['thr'])})"


def cq_no_conflict(case, claim, ev):
    c = claim.content
    for p in case.spec:
        d = parse_spec(p.text)
        if d and d["rid"] != c["rid"] and d["param"] == c["param"] and (d["op"], d["thr"]) != (c["op"], c["thr"]):
            return False, f"conflicting statement in {p.pid}"
    return True, "no conflicting statement found"


def cq_value_grounded(case, claim, ev):
    q = (ev or {}).get("quote", "")
    d = parse_design(q)
    ok = bool(q) and q in _passage(case, claim.refs["passage"]) and bool(d) and d["value"] == claim.content["value"]
    return ok, "value grounded in datasheet" if ok else "claimed value not grounded in datasheet quote"


def cq_comparison_correct(case, claim, ev):
    c = claim.content
    ok = evaluate(c["op"], c["value"], c["thr"]) == (c["result"] == "pass")
    return ok, "comparison recomputed identically" if ok else "recomputed comparison disagrees"


SCHEMES = {
    "extraction_from_source": {
        "cqs": {"CQ1": cq_quote_grounded, "CQ2": cq_value_fidelity, "CQ3": cq_no_conflict},
        "burden": {"A": ["CQ1", "CQ2", "CQ3"], "B": ["CQ1", "CQ2"], "C": []}},
    "verification_result": {
        "cqs": {"CQ1": cq_value_grounded, "CQ2": cq_comparison_correct},
        "burden": {"A": ["CQ1", "CQ2"], "B": ["CQ2"], "C": []}},
}


class DialogueEngine:
    """Imposes the protocol: admissibility rules + external checking of every answer."""

    def __init__(self, case: Case):
        self.case, self.claims, self.transcript = case, {}, []

    def submit(self, m: Move) -> None:
        c = self.claims.get(m.claim_id)
        if m.kind == "CLAIM":
            if m.speaker != "proponent" or c is not None:
                raise Inadmissible("CLAIM must come from the proponent and be new")
            fresh = copy.deepcopy(m.payload)      # engine owns the state: reset on registration
            fresh.status, fresh.pending, fresh.satisfied, fresh.failures, fresh.quote = "OPEN", None, [], [], None
            self.claims[m.claim_id] = fresh
        else:
            if c is None:
                raise Inadmissible("unknown claim")
            if c.status in TERMINAL:
                raise Inadmissible(f"claim already {c.status}")
            if m.kind == "WHY":
                if m.speaker != "challenger" or c.pending or m.cq not in SCHEMES[c.scheme]["cqs"] \
                        or m.cq in c.satisfied:
                    raise Inadmissible("illegal WHY (role / pending / unknown or already-answered CQ)")
                c.pending = m.cq
            elif m.kind == "GROUND":
                if m.speaker != "proponent" or c.pending != m.cq:
                    raise Inadmissible("GROUND must answer the pending WHY, from the proponent")
                q = (m.payload or {}).get("quote")
                if q is not None and c.quote is not None and q != c.quote:      # commitment consistency rule
                    ok, detail = False, "evidence differs from the quote already committed"
                else:
                    c.quote = c.quote if q is None else q
                    ok, detail = SCHEMES[c.scheme]["cqs"][m.cq](self.case, c, m.payload)
                c.pending = None
                (c.satisfied if ok else c.failures).append(m.cq if ok else (m.cq, detail))
                if not ok:
                    c.status = "REFUTED"
            elif m.kind == "RETRACT":
                if m.speaker != "proponent":
                    raise Inadmissible("only the proponent can retract")
                c.status = "RETRACTED"
            elif m.kind == "CLOSE":
                if m.speaker != "orchestrator":
                    raise Inadmissible("only the orchestrator closes")
                required = SCHEMES[c.scheme]["burden"][c.crit]
                if c.pending:
                    c.status = "UNSUPPORTED"
                elif not required:
                    c.status = "UNCHALLENGED"
                else:
                    c.status = "VERIFIED" if all(q in c.satisfied for q in required) else "UNSUPPORTED"
            else:
                raise Inadmissible("unknown move")
        self.transcript.append(m)


class SimProponent:
    """Simulated LLM proponent: states claims from the chain's outputs and defends them.
    May fabricate quotes (a classic LLM failure)."""

    def __init__(self, case: Case, p_fabricate: float = 0.15, seed: int = 0):
        self.case, self.p, self.rng = case, p_fabricate, random.Random(seed)

    def claims(self, run) -> list[Claim]:
        out = []
        for eid, el in run.elements.items():
            if el.kind == "req":
                out.append(Claim(f"ext:{el.req_id}", "extraction_from_source", el.content,
                                 {"passage": el.req_id}, el.criticality or "A", eid))
            elif el.kind == "ver" and f"val:{el.req_id}" in run.elements:
                req, val = run.elements[f"req:{el.req_id}"].content, run.elements[f"val:{el.req_id}"].content
                out.append(Claim(f"ver:{el.req_id}", "verification_result",
                                 {"rid": el.req_id, "op": req["op"], "thr": req["thr"], "value": val["value"],
                                  "result": el.content["result"]}, {"passage": f"D-{el.req_id}"},
                                 run.elements[f"req:{el.req_id}"].criticality or "A", eid))
        return out

    def answer(self, claim: Claim, cq: str) -> dict:
        if cq == "CQ3":
            return {"searched": True}
        if self.rng.random() < self.p:           # fabricated quote: rendered from the claim, not the source
            c = claim.content
            if claim.scheme == "extraction_from_source":
                return {"quote": f"[{c['rid']}] The {c['param']} shall be {WORDS[c['op']]} {c['thr']:g} {c['unit']}. Criticality: {c['crit']}."}
            return {"quote": f"[D-{c['rid']}] Measured value: {c['value']:g} unit."}
        return {"quote": _passage(self.case, claim.refs["passage"])}


@dataclass
class DialogueResult:
    claims: dict
    transcript: list
    n_moves: int
    violations: list = field(default_factory=list)

    def status_by_eid(self) -> dict:
        return {c.eid: c.status for c in self.claims.values()}

    def refuted_rids(self) -> set:
        return {c.cid.split(":")[1] for c in self.claims.values() if c.status == "REFUTED"}


def run_dialogue(case: Case, run, proponent: SimProponent) -> DialogueResult:
    eng = DialogueEngine(case)
    for claim in proponent.claims(run):
        eng.submit(Move("CLAIM", "proponent", claim.cid, payload=claim))
        for cq in SCHEMES[claim.scheme]["burden"][claim.crit]:        # burden ∝ criticality
            eng.submit(Move("WHY", "challenger", claim.cid, cq))
            eng.submit(Move("GROUND", "proponent", claim.cid, cq, proponent.answer(claim, cq)))
            if eng.claims[claim.cid].status == "REFUTED":
                break
        if eng.claims[claim.cid].status not in TERMINAL:
            eng.submit(Move("CLOSE", "orchestrator", claim.cid))
    return DialogueResult(eng.claims, eng.transcript, len(eng.transcript), check_conformity(case, eng.transcript))


def check_conformity(case: Case, moves: list) -> list:
    """Replay a transcript through a fresh engine: conformity is verified outside the model."""
    eng, violations = DialogueEngine(case), []
    for i, m in enumerate(moves):
        try:
            eng.submit(m)
        except Inadmissible as e:
            violations.append((i, m.kind, m.claim_id, str(e)))
    return violations
