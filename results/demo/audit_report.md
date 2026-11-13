# Audit report — case-11

**Decision:** ACCEPT  (gold: REJECT)  
**Natural variability (baseline flip rate p0):** 0.25  
**Replays spent:** 728  
**Explanation sufficient (keep-only replay):** True (rate 0.70)

## Decisive requirements (replay-verified)

| requirement | criticality | statement | effect over baseline | 95% CI | perturbation | evidence |
|---|---|---|---|---|---|---|
| R1 | A | power consumption <= 5 W | +0.75 | [0.51, 1.00] | flip | VERIFIED / VERIFIED |
| R2 | B | MTBF <= 5 h | +0.75 | [0.51, 1.00] | flip | VERIFIED / VERIFIED |
| R3 | B | efficiency <= 50 % | +0.75 | [0.51, 1.00] | flip | VERIFIED / VERIFIED |
| R6 | A | burst pressure <= 3.09 bar | +0.75 | [0.51, 1.00] | flip | REFUTED / VERIFIED |
| R7 | A | sampling frequency <= 50 Hz | +0.75 | [0.51, 1.00] | flip | VERIFIED / VERIFIED |
| R8 | A | response time >= 15 ms | +0.75 | [0.51, 1.00] | flip | VERIFIED / VERIFIED |
| R9 | B | coolant temperature <= 40 °C | +0.75 | [0.51, 1.00] | flip | VERIFIED / VERIFIED |
| R10 | A | supply voltage >= 25 V | +0.65 | [0.60, 0.98] | flip | VERIFIED / VERIFIED |

## Decisive information elements

- `ver:R1` (ver, by verifier) — effect +0.75 via `flip_result`
- `src:R1` (spec, by input) — effect +0.75 via `flip_op`
- `val:R1` (val, by reader) — effect +0.75 via `remove`
- `des:R1` (design, by input) — effect +0.75 via `remove`
- `req:R1` (req, by extractor) — effect +0.75 via `flip_op`
- `des:R10` (design, by input) — effect +0.75 via `remove`
- `val:R10` (val, by reader) — effect +0.75 via `remove`
- `ver:R10` (ver, by verifier) — effect +0.75 via `flip_result`
- `req:R10` (req, by extractor) — effect +0.75 via `flip_op`
- `des:R2` (design, by input) — effect +0.75 via `remove`
- `req:R2` (req, by extractor) — effect +0.75 via `flip_op`
- `val:R2` (val, by reader) — effect +0.75 via `remove`
- `src:R2` (spec, by input) — effect +0.75 via `flip_op`
- `ver:R2` (ver, by verifier) — effect +0.75 via `flip_result`
- `src:R3` (spec, by input) — effect +0.75 via `flip_op`
- `req:R3` (req, by extractor) — effect +0.75 via `flip_op`
- `val:R3` (val, by reader) — effect +0.75 via `remove`
- `ver:R3` (ver, by verifier) — effect +0.75 via `flip_result`
- `des:R3` (design, by input) — effect +0.75 via `remove`
- `des:R6` (design, by input) — effect +0.75 via `remove`
- `val:R6` (val, by reader) — effect +0.75 via `remove`
- `req:R6` (req, by extractor) — effect +0.75 via `revert`
- `ver:R6` (ver, by verifier) — effect +0.75 via `flip_result`
- `des:R7` (design, by input) — effect +0.75 via `remove`
- `src:R7` (spec, by input) — effect +0.75 via `flip_op`
- `val:R7` (val, by reader) — effect +0.75 via `remove`
- `req:R7` (req, by extractor) — effect +0.75 via `flip_op`
- `ver:R7` (ver, by verifier) — effect +0.75 via `flip_result`
- `req:R8` (req, by extractor) — effect +0.75 via `flip_op`
- `des:R8` (design, by input) — effect +0.75 via `remove`
- `src:R8` (spec, by input) — effect +0.75 via `flip_op`
- `ver:R8` (ver, by verifier) — effect +0.75 via `flip_result`
- `val:R8` (val, by reader) — effect +0.75 via `remove`
- `ver:R9` (ver, by verifier) — effect +0.75 via `flip_result`
- `des:R9` (design, by input) — effect +0.75 via `remove`
- `src:R9` (spec, by input) — effect +0.75 via `flip_op`
- `req:R9` (req, by extractor) — effect +0.75 via `flip_op`
- `val:R9` (val, by reader) — effect +0.75 via `remove`
- `src:R10` (spec, by input) — effect +0.65 via `flip_op`

## Faithfulness check of the agent's own textual justification

- cited by the decider: ['R1', 'R10', 'R2', 'R3', 'R6', 'R7', 'R8', 'R9']
- replay-verified: ['R1', 'R10', 'R2', 'R3', 'R6', 'R7', 'R8', 'R9']
- **justification faithful:** True

## Dialogue (claims checked outside the model)

- claim status: {'UNCHALLENGED': 4, 'VERIFIED': 15, 'REFUTED': 1}
- moves: 105; protocol violations: 0
- ⚠ `ext:R6` REFUTED: [('CQ2', "claimed (<= 3.09) != quote (('<=', 2.0))")]

## Audit flags

- **Decisive AND refuted → prime suspects for the decision error:** ['R6']
