import random

import pytest

from tracemas.bench import e1_faithfulness, make_injection, prf
from tracemas.corpus import make_case
from tracemas.dialogue import (DialogueEngine, Inadmissible, Move, SimProponent, check_conformity, run_dialogue)
from tracemas.explain import Config, PerturbationExplainer, oracle_explanation
from tracemas.llm import NoiseConfig, SimulatedLLM
from tracemas.pipeline import Pipeline, mutate
from tracemas.provenance import to_dot, to_prov_json
from tracemas.stats import fisher_one_sided, wilson
from tracemas.types import Case, Intervention

ZERO = lambda: Pipeline(SimulatedLLM(NoiseConfig.zero()))


@pytest.mark.parametrize("seed", range(20))
def test_noise_free_chain_matches_gold(seed):
    case = make_case(seed)
    assert ZERO().run(case).verdict == case.gold["decision"]


def test_case_roundtrip():
    c = make_case(3)
    assert Case.from_dict(c.to_dict()).spec == c.spec


def test_provenance_dag_and_irrelevant_passages_excluded():
    case = make_case(1)
    run = ZERO().run(case)
    anc = run.ancestors("dec:final")
    assert "src:N1" in run.elements and "src:N1" not in anc     # distractor passage is not upstream
    assert {"ver:R1", "req:R1", "val:R1", "src:R1", "des:R1", "pol"} <= anc
    doc = to_prov_json(run)
    assert "tm:dec:final" in doc["entity"] and doc["used"]
    assert to_dot(run, {"ver:R1"}).startswith("digraph")


def test_interventions_remove_alter_inject():
    case = make_case(2)
    p = ZERO()
    base = p.run(case)
    r = p.run(case, 0, {"src:R1": Intervention("remove")})
    assert "req:R1" not in r.elements and "ver:R1" not in r.elements and "src:R1" in r.removed
    r = p.run(case, 0, {"ver:R1": Intervention("alter", "flip_result")})
    assert r.elements["ver:R1"].content != base.elements["ver:R1"].content
    inj = {"req:R1": Intervention("inject", value={**base.elements["req:R1"].content, "thr": 1e9, "op": "<="})}
    assert p.run(case, 0, inj).elements["req:R1"].content["thr"] == 1e9
    with pytest.raises(ValueError):
        mutate("ver", {"result": "pass"}, "nonsense")


def test_replays_are_reproducible_per_seed_and_vary_across_seeds():
    case, llm = make_case(1), SimulatedLLM(NoiseConfig().scaled(4))
    a = [Pipeline(llm).run(case, 5).verdict for _ in range(3)]
    assert len(set(a)) == 1
    runs = {tuple(sorted((k, str(e.content)) for k, e in Pipeline(llm).run(case, s).elements.items())) for s in range(10)}
    assert len(runs) > 1


def test_stats():
    assert fisher_one_sided(8, 8, 0, 16) < 0.001
    assert fisher_one_sided(1, 8, 2, 16) > 0.3
    lo, hi = wilson(7, 10)
    assert lo < 0.7 < hi


@pytest.mark.parametrize("seed", [2, 3, 5])
def test_hierarchical_replay_matches_oracle(seed):
    case = make_case(seed)
    _, truth, _ = oracle_explanation(ZERO(), case)
    exp = PerturbationExplainer(Pipeline(SimulatedLLM()), Config(), seed0=seed * 1000).explain(case)
    assert prf(exp.group_ids, truth)[2] >= 0.9


def test_redundant_causes_found_by_sufficiency_not_by_flat_necessity():
    # REJECT with two failing critical requirements: each removal alone leaves the decision unchanged.
    case = next(c for c in (make_case(s, scenario="reject") for s in range(60)) if len(c.gold["failing_critical"]) == 2)
    _, truth, _ = oracle_explanation(ZERO(), case)
    assert set(case.gold["failing_critical"]) == truth
    flat = PerturbationExplainer(Pipeline(SimulatedLLM()), Config(crit_aware=False, early_stop=False)).explain(case, False)
    hier = PerturbationExplainer(Pipeline(SimulatedLLM()), Config()).explain(case, True)
    assert flat.group_ids == set()                   # necessity-only misses overdetermined decisions
    assert hier.group_ids == truth and hier.sufficient


def test_hierarchical_is_cheaper_than_flat_on_reject_cases():
    case = make_case(5)
    assert case.gold["decision"] == "REJECT"
    pipe = Pipeline(SimulatedLLM())
    h = PerturbationExplainer(pipe, Config()).explain(case, True)
    f = PerturbationExplainer(pipe, Config(crit_aware=False, early_stop=False)).explain(case, False)
    assert h.replays < 0.6 * f.replays and h.group_ids == f.group_ids


def test_injected_error_is_localised():
    nf = ZERO()
    for s in range(100, 160):
        case = make_case(s)
        inj = make_injection(case, nf, random.Random(s))
        if inj:
            ivs, rid = inj
            pipe = Pipeline(SimulatedLLM(NoiseConfig().scaled(0.5)))
            exp = PerturbationExplainer(pipe, Config(), ivs).explain(case)
            assert rid in exp.group_ids
            return
    pytest.fail("no injectable case found")


def test_dialogue_rejects_inadmissible_moves():
    case = make_case(1)
    run = ZERO().run(case)
    claim = SimProponent(case).claims(run)[0]
    eng = DialogueEngine(case)
    with pytest.raises(Inadmissible):
        eng.submit(Move("WHY", "challenger", claim.cid, "CQ1"))          # unknown claim
    eng.submit(Move("CLAIM", "proponent", claim.cid, payload=claim))
    with pytest.raises(Inadmissible):
        eng.submit(Move("GROUND", "proponent", claim.cid, "CQ1", {}))    # no pending WHY
    with pytest.raises(Inadmissible):
        eng.submit(Move("WHY", "proponent", claim.cid, "CQ1"))           # wrong role
    eng.submit(Move("WHY", "challenger", claim.cid, "CQ1"))
    with pytest.raises(Inadmissible):
        eng.submit(Move("WHY", "challenger", claim.cid, "CQ2"))          # WHY already pending


def test_dialogue_refutes_hallucinated_threshold_and_fabricated_quote():
    case = make_case(4)
    run = ZERO().run(case)
    eid = next(e for e, el in run.elements.items() if el.kind == "req" and el.criticality == "A")
    run.elements[eid].content["thr"] *= 1.5                              # hallucination
    d = run_dialogue(case, run, SimProponent(case, p_fabricate=0.0))
    assert run.elements[eid].req_id in d.refuted_rids() and not d.violations
    d2 = run_dialogue(case, ZERO().run(case), SimProponent(case, p_fabricate=1.0))   # fabricated quotes on design claims
    assert any(c.status == "REFUTED" for c in d2.claims.values())


def test_burden_of_proof_scales_with_criticality():
    case = make_case(6)
    d = run_dialogue(case, ZERO().run(case), SimProponent(case, 0.0))
    moves = {}
    for c in d.claims.values():
        if c.scheme == "extraction_from_source":
            moves.setdefault(c.crit, set()).add(sum(m.claim_id == c.cid for m in d.transcript))
    assert max(moves["A"]) > max(moves["B"]) > max(moves["C"])


def test_conformity_check_flags_forged_transcript():
    case = make_case(1)
    d = run_dialogue(case, ZERO().run(case), SimProponent(case, 0.0))
    forged = list(d.transcript) + [Move("GROUND", "proponent", next(iter(d.claims)), "CQ1", {"quote": "x"})]
    assert check_conformity(case, d.transcript) == [] and check_conformity(case, forged)


def test_e1_small_run_ordering():
    r = e1_faithfulness(n_cases=4, seed0=0)
    assert r["replay_hier_crit"]["f1"] >= r["provenance_ancestors"]["f1"]
    assert r["replay_hier_crit"]["replays"] < r["replay_flat"]["replays"]


def test_commitment_consistency_blocks_switching_quotes():
    """Regression found by benchmark E4: a proponent could give an honest quote for CQ1 and a different,
    claim-matching quote for CQ2. The engine now binds later answers to the first committed quote."""
    case = make_case(4)
    run = ZERO().run(case)
    eid = next(e for e, el in run.elements.items() if el.kind == "req" and el.criticality == "A")
    run.elements[eid].content["thr"] *= 1.5
    claim = next(c for c in SimProponent(case).claims(run) if c.eid == eid)
    honest = {"quote": next(p.text for p in case.spec if p.pid == claim.refs["passage"])}
    c = claim.content
    forged = {"quote": f"[{c['rid']}] The {c['param']} shall be {'at most' if c['op'] == '<=' else 'at least'} {c['thr']:g} {c['unit']}. Criticality: {c['crit']}."}
    eng = DialogueEngine(case)
    eng.submit(Move("CLAIM", "proponent", claim.cid, payload=claim))
    eng.submit(Move("WHY", "challenger", claim.cid, "CQ1")); eng.submit(Move("GROUND", "proponent", claim.cid, "CQ1", honest))
    eng.submit(Move("WHY", "challenger", claim.cid, "CQ2")); eng.submit(Move("GROUND", "proponent", claim.cid, "CQ2", forged))
    assert eng.claims[claim.cid].status == "REFUTED"
