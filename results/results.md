# TRACE-MAS benchmark results (simulated agents)

## E1 — Faithfulness vs noise-free ground truth (requirement-level)

| method | precision | recall | F1 | exact | avg #groups | avg replays |
|---|---|---|---|---|---|---|
| text_justification | 0.896 | 0.843 | 0.837 | 0.792 | 3.875 | 1 |
| provenance_ancestors | 0.475 | 1.0 | 0.579 | 0.0 | 10 | 1 |
| replay_flat | 0.75 | 0.75 | 0.75 | 0.75 | 4.25 | 1734 |
| replay_hier_uniform | 1.0 | 1.0 | 1.0 | 1.0 | 4.75 | 543.917 |
| replay_hier_crit | 1.0 | 1.0 | 1.0 | 1.0 | 4.75 | 512.75 |

## E2 — Localising an injected (hallucinated) requirement (40 wrong decisions)

| method | hit-rate | avg #groups flagged | precision if hit | avg replays |
|---|---|---|---|---|
| text_justification | 0.725 | 2.175 | 0.561 | 1 |
| provenance_ancestors | 1.0 | 10 | 0.1 | 1 |
| replay_flat | 1.0 | 2.45 | 0.806 | 1748 |
| replay_hier_uniform | 1.0 | 2.45 | 0.806 | 387.75 |
| replay_hier_crit | 1.0 | 2.45 | 0.806 | 373.05 |
| dialogue_refutation | 1.0 | 1.7 | 0.729 | 0 |

## E3 — Natural variability vs noise level

| noise ×| natural flip rate p0 | F1 (replay_hier_crit) | replays |
|---|---|---|---|
| 0.0 | 0.0 | 1.0 | 431.3 |
| 0.5 | 0.073 | 1.0 | 542.7 |
| 1.0 | 0.104 | 0.994 | 649.1 |
| 2.0 | 0.224 | 0.994 | 728 |
| 3.0 | 0.276 | 0.859 | 676.3 |

## E4 — Dialogue protocol (burden of proof ∝ criticality)

- extraction errors refuted: 8, missed: 7, false refutations: 0, recall: 0.533
- recall by criticality (errors in C-claims are deliberately unchallenged): {'A': 1.0, 'B': 1.0, 'C': 0.0}
- moves per claim by criticality: {'A': 7.88, 'B': 5.97, 'C': 2}
- protocol violations found by external conformity check: 0
