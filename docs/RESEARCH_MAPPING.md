# Mapping to the PhD call ("Beyond the Output", CentraleSupélec × ALTEN)

| Call element | Where in this repo |
|---|---|
| Multi-agent chain, requirements extracted/checked from technical documents | `pipeline.py`, `corpus.py` |
| Information elements & granularity (RQ1) | `types.Element`, per-requirement element ids, `docs/METHODOLOGY.md §2` |
| Provenance graph inspired by PROV-AGENT | `provenance.py` (PROV-JSON, DOT), `Run.ancestors` |
| Perturbation-based faithfulness: removal / alteration / injection, replays (RQ2) | `explain.py`, `pipeline.mutate`, `Intervention` |
| Natural non-reproducibility measured before interpreting perturbations | baseline flip rate p0, Fisher test, **E3** |
| Cost of perturbation: provenance restriction, grouped ablation | hierarchical explainer, early stopping, E1 replays |
| Criticality vs severity shaping evidence | replay budget ∝ criticality; dialogue burden of proof ∝ criticality (severity = future work) |
| Dialogue protocols imposed on LLMs, argument schemes, critical questions (RQ3) | `dialogue.py` |
| Benchmark of injected known errors; baselines (original chain, provenance, textual justification) | `bench.py` E1/E2 |
| Audit usefulness study with engineers (RQ4) | not implemented — protocol sketched in README Roadmap |
| Failure-attribution literature (Zhang et al.) | contrast: explains *any* decision (correct or not) w.r.t. requirements, not only failures |
