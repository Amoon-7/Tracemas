"""Core data types: documents, cases, and provenance elements."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional

CRIT_WEIGHT = {"A": 1.0, "B": 0.6, "C": 0.25}  # criticality -> evidence weight


@dataclass(frozen=True)
class Passage:
    pid: str
    text: str


@dataclass
class Case:
    """A requirements-driven design-compliance case (spec + design + policy)."""
    case_id: str
    spec: list
    design: list
    policy: dict
    gold: dict

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Case":
        return Case(d["case_id"], [Passage(**p) for p in d["spec"]],
                    [Passage(**p) for p in d["design"]], d["policy"], d["gold"])


@dataclass
class Element:
    """An *information element*: the unit of explanation (granularity = RQ1).

    kind: spec | design | req | val | ver | policy | decision
    """
    eid: str
    kind: str
    content: Any
    agent: str
    task: str
    used: tuple = ()
    req_id: Optional[str] = None
    criticality: Optional[str] = None
    perturbed: Optional[str] = None


@dataclass
class Intervention:
    """A do()-style intervention on one element during a replay."""
    op: str                      # remove | alter | inject
    variant: Optional[str] = None  # for alter: flip_op, scale_up, ...
    value: Any = None            # for inject
