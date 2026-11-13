"""PROV-AGENT-inspired provenance export (W3C PROV-JSON flavour) and Graphviz DOT."""
from __future__ import annotations

from .pipeline import Run


def to_prov_json(run: Run, claim_status: dict | None = None) -> dict:
    claim_status = claim_status or {}
    doc = {"prefix": {"tm": "https://github.com/amoon-le-magnifique/tracemas-audit#"},
           "entity": {}, "activity": {}, "agent": {}, "used": {}, "wasGeneratedBy": {}, "wasAssociatedWith": {}}
    for eid, e in run.elements.items():
        doc["entity"][f"tm:{eid}"] = {"tm:kind": e.kind, "tm:content": e.content, "tm:requirement": e.req_id,
                                       "tm:criticality": e.criticality, "tm:perturbed": e.perturbed,
                                       "tm:claim_status": claim_status.get(eid)}
        act = f"tm:act:{eid}"
        doc["activity"][act] = {"tm:task": e.task}
        doc["agent"][f"tm:agent:{e.agent}"] = {}
        doc["wasGeneratedBy"][f"_:g:{eid}"] = {"prov:entity": f"tm:{eid}", "prov:activity": act}
        doc["wasAssociatedWith"][f"_:a:{eid}"] = {"prov:activity": act, "prov:agent": f"tm:agent:{e.agent}"}
        for i, u in enumerate(e.used):
            doc["used"][f"_:u:{eid}:{i}"] = {"prov:activity": act, "prov:entity": f"tm:{u}"}
    return doc


def to_dot(run: Run, decisive: set | None = None, claim_status: dict | None = None) -> str:
    decisive, claim_status = decisive or set(), claim_status or {}
    anc = run.ancestors("dec:final") | {"dec:final"}
    shape = {"spec": "note", "design": "note", "policy": "note", "req": "box", "val": "box", "ver": "box", "decision": "doubleoctagon"}
    L = ["digraph provenance {", "  rankdir=LR; node [fontname=Helvetica,fontsize=10,style=filled,fillcolor=white];"]
    for eid in sorted(anc):
        e = run.elements[eid]
        color = "#f4a582" if eid in decisive else "white"
        cs = claim_status.get(eid)
        label = f"{eid}\\n{e.agent}" + (f"\\n[{cs}]" if cs else "")
        L.append(f'  "{eid}" [shape={shape[e.kind]},fillcolor="{color}",label="{label}"];')
    for eid in sorted(anc):
        for u in run.elements[eid].used:
            L.append(f'  "{u}" -> "{eid}";')
    L.append("}")
    return "\n".join(L)
