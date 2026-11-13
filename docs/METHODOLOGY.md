# Methodology

## 1. Setting
A requirements-driven chain of four agents (Extractor → Reader → Verifier → Decider) checks a design datasheet
against a specification whose requirements carry a criticality (A > B > C). A policy decides what is rejected
(default: any failed/unverifiable A or B requirement). Constraints are explicit, so compliance and the origin of an
error are objectively checkable.

## 2. Information elements and provenance (RQ1)
Granularity = one element per agent output **per requirement**: `src` (spec passage), `des` (datasheet passage),
`req` (extracted requirement), `val` (read value), `ver` (verification result), `pol` (policy), `dec` (decision).
Element ids are stable across runs (`req:R3`), so executions can be replayed and compared. Each element records the
elements it `used` → a PROV-style DAG (`tracemas.provenance`, PROV-JSON + DOT export; inspired by PROV-AGENT).
*Too fine* (tokens) makes the candidate space intractable, *too coarse* (whole agent output) is useless for an auditor;
the per-requirement element is the compromise tested here. Elements are grouped by requirement id for grouped ablation.

## 3. Faithfulness by controlled perturbation (RQ2)
An explanation = the elements whose do()-style perturbation changes the decision **beyond natural variability**.
* Perturbations: `remove`, type-specific counterfactual `alter` (flip operator, scale value, flip verification,
  relax policy), `inject` (known error), `revert` (undo a persistent error).
* **Natural variability first.** `k` unperturbed replays estimate a baseline flip rate p0. A perturbation is
  significant if its flip rate exceeds p0 by `min_effect` *and* a one-sided Fisher exact test gives p < α.
* **Overdetermination.** A necessity test alone cannot explain a REJECT caused by two independent failing critical
  requirements (removing either one leaves the verdict unchanged). The explainer therefore adds a **sufficiency-alone**
  test (keep only group g, remove the other requirements; compare with the all-removed baseline) and drills down into
  elements *under that held contingency*. (Flat single-element necessity misses these cases: see E1.)
* **Sufficiency check.** Keeping only the explanation and removing all other requirements should preserve the decision
  about as often as an unperturbed replay.
* The provenance graph restricts candidates to **ancestors of the decision** (distractor passages are never tested).

## 4. Cost control
Hierarchical (grouped) ablation → drill down only into decisive groups; sequential early stopping; replay budget
**proportional to criticality** (`n = n_min + (n_max-n_min)·w(crit)`, w = 1 / 0.6 / 0.25 for A / B / C).

## 5. Dialogue protocol (RQ3, second direction)
Orchestrator-imposed moves `CLAIM / WHY / GROUND / RETRACT / CLOSE`; claims instantiate argument schemes
(*extraction-from-source*, *verification-result*) with critical questions checked by deterministic code **outside the
model**. Burden of proof ∝ criticality (A: all CQs, B: core CQs, C: unchallenged). A *commitment consistency* rule binds
later answers to the first quote (found as a protocol hole by benchmark E4 and fixed; regression-tested). Conformity of any
transcript is re-checked by replaying it through a fresh engine. The dialogue is **not** a proof of faithfulness: it
produces checked claims that are linked to the provenance graph; replays remain the faithfulness test.

## 6. Evaluation (hierarchical, as in the call)
| level | experiment | question |
|---|---|---|
| faithfulness | E1 (vs noise-free exhaustive oracle), E2 (injected known errors) | does the explanation point at what really determined the decision? |
| coverage / diagnosis | E2 hit-rate, explanation size, E4 per-criticality recall | are critical errors found, with a short explanation? |
| cost | replays per decision, criticality-aware budget | what does evidence cost? |
| variability | E3 | how does natural non-determinism affect faithfulness? |
| usefulness for audit | *not covered* — needs a user study (see Roadmap) | do explanations improve audit, not just trust? |
Baselines: the agent's own **textual justification**, **provenance ancestors** (all upstream), **flat replay**.

## 7. Threats to validity
* Agents are **simulated** (controllable noise, unfaithful justifications by construction); numbers show the *method's*
  behaviour under assumptions, not real-LLM performance.
* The synthetic domain is small; single-requirement elements and a threshold-style policy are simpler than industrial specs.
* Real LLM agents are non-reproducible even at temperature 0; `AnthropicLLM` makes this measurable (E3 protocol) but results
  with real models are not reported here.
