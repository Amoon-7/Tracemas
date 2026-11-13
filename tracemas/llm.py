"""LLM backends.

* ``SimulatedLLM``  – deterministic-given-seed agents with configurable noise
  (hallucinated thresholds, wrong comparisons, *unfaithful justifications*).
  Lets us study explanation methods with controllable ground truth.
* ``AnthropicLLM``  – drop-in adapter for a real model (optional dependency).

Interface: ``complete(task, payload, key, seed) -> JSON-like``.
"""
from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass, replace
from typing import Any, Protocol

from .parsing import WORDS, evaluate, parse_design, parse_spec


class LLM(Protocol):
    def complete(self, task: str, payload: dict, key: str, seed: int) -> Any: ...


@dataclass
class NoiseConfig:
    p_hallucinate: float = 0.02     # extractor hallucinates a threshold
    p_flip_op: float = 0.005        # extractor inverts the comparison operator
    p_read_err: float = 0.01        # wrong measured value read from datasheet
    p_verify_err: float = 0.01      # wrong pass/fail comparison
    p_decide_err: float = 0.003     # wrong final verdict
    p_unfaithful: float = 0.30      # textual justification cites the wrong elements

    def scaled(self, s: float) -> "NoiseConfig":
        d = {k: min(1.0, v * s) for k, v in self.__dict__.items() if k != "p_unfaithful"}
        return replace(self, **d)

    @staticmethod
    def zero() -> "NoiseConfig":
        return NoiseConfig(0, 0, 0, 0, 0, 0)


def _wrong_factor(rng: random.Random) -> float:
    return rng.choice([rng.uniform(0.5, 0.85), rng.uniform(1.15, 1.6)])


class SimulatedLLM:
    def __init__(self, noise: NoiseConfig | None = None):
        self.noise = noise or NoiseConfig()

    def complete(self, task: str, payload: dict, key: str, seed: int) -> Any:
        rng = random.Random(f"{seed}|{task}|{key}")   # replays differ only via `seed`
        return getattr(self, f"_{task}")(payload, rng)

    def _extract(self, p, rng):
        d = parse_spec(p["text"])
        if d is None:
            return None
        if rng.random() < self.noise.p_hallucinate:
            d["thr"] = round(d["thr"] * _wrong_factor(rng), 2)
        if rng.random() < self.noise.p_flip_op:
            d["op"] = ">=" if d["op"] == "<=" else "<="
        return d

    def _read_value(self, p, rng):
        d = parse_design(p["text"])
        if d is None:
            return None
        v = d["value"]
        if rng.random() < self.noise.p_read_err:
            v = round(v * _wrong_factor(rng), 2)
        return {"value": v}

    def _verify(self, p, rng):
        ok = evaluate(p["req"]["op"], p["value"], p["req"]["thr"])
        if rng.random() < self.noise.p_verify_err:
            ok = not ok
        return {"result": "pass" if ok else "fail"}

    def _decide(self, p, rng):
        reject_on = (p.get("policy") or {"reject_on": ["A", "B"]})["reject_on"]
        trig = sorted(r for r, v in p["verifications"].items()
                      if v["crit"] in reject_on and v["result"] in ("fail", "missing"))
        verdict = "REJECT" if trig else "ACCEPT"
        if rng.random() < self.noise.p_decide_err:
            verdict = "ACCEPT" if verdict == "REJECT" else "REJECT"
        cited = trig if trig else sorted(r for r, v in p["verifications"].items() if v["crit"] in reject_on)
        if p["verifications"] and rng.random() < self.noise.p_unfaithful:
            # plausible-but-unfaithful justification: cites a salient requirement instead
            cited = [rng.choice(sorted(p["verifications"]))]
        return {"verdict": verdict, "cited_rids": cited}


PROMPTS = {
    "extract": 'Extract the requirement from this specification passage. Reply with ONLY JSON '
               '{{"rid":str,"param":str,"op":"<="|">=","thr":number,"unit":str,"crit":"A"|"B"|"C"}} or null if no requirement.\n{payload}',
    "read_value": 'Read the measured value from this datasheet passage. Reply with ONLY JSON {{"value":number}} or null.\n{payload}',
    "verify": 'Does value satisfy the requirement (op, thr)? Reply with ONLY JSON {{"result":"pass"|"fail"}}.\n{payload}',
    "decide": 'Given verifications and policy (reject if a failed/missing requirement has criticality in reject_on), '
              'decide. Reply with ONLY JSON {{"verdict":"ACCEPT"|"REJECT","cited_rids":[str]}} where cited_rids are the '
              'requirements your decision relies on.\n{payload}',
}


class AnthropicLLM:
    """Real-model backend (pip install anthropic; set ANTHROPIC_API_KEY)."""

    def __init__(self, model: str | None = None, max_tokens: int = 300):
        import anthropic  # lazy import: optional dependency
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("TRACEMAS_MODEL", "claude-sonnet-5-5")
        self.max_tokens = max_tokens

    def complete(self, task, payload, key, seed):
        msg = self.client.messages.create(
            model=self.model, max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": PROMPTS[task].format(payload=json.dumps(payload, ensure_ascii=False))}])
        text = msg.content[0].text.strip()
        m = re.search(r"(\{.*\}|null)", text, re.S)
        return json.loads(m.group(1)) if m else None
