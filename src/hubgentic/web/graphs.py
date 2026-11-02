"""Graph payloads (Cytoscape.js elements) for the Explorer and Ontology views."""
from __future__ import annotations

from typing import Any

from hubgentic.lineage.model import UnifiedEntity
from hubgentic.resolution.base import RecordRef


def _enum(v: Any) -> str:
    return getattr(v, "value", v)


def _rid(r: RecordRef) -> str:
    return f"rec:{r.source}:{r.source_object}:{r.source_key}"


def _record(r: RecordRef, kind: str) -> dict:
    return {"data": {
        "id": _rid(r), "kind": kind, "source": r.source,
        "label": f"{r.source_object} · {r.source_key}",
        "detail": f"{r.source}.{r.source_object}[{r.source_key}]",
    }}


def entity_graph(result: UnifiedEntity) -> list[dict]:
    """The resolved entity, the source records it was assembled from, the
    match rules that linked them, rejected candidates, and relationships."""
    res = result.resolution
    canon = result.canonical
    title = canon["legal_name"].value if "legal_name" in canon else result.entity_type
    els: list[dict] = [{"data": {
        "id": "entity", "kind": "entity", "label": str(title),
        "detail": f"{result.entity_type} · resolved from {len(res.cluster_records)} record(s)",
    }}]
    seen = {"entity"}

    def add(node: dict) -> None:
        if node["data"]["id"] not in seen:
            seen.add(node["data"]["id"])
            els.append(node)

    for r in res.cluster_records:
        add(_record(r, "record"))
        els.append({"data": {"id": f"m:{_rid(r)}", "source": "entity", "target": _rid(r),
                             "kind": "member", "label": ""}})
    for i, m in enumerate(res.supporting_matches):
        els.append({"data": {
            "id": f"match:{i}", "source": _rid(m.left), "target": _rid(m.right), "kind": "match",
            "label": f"{m.rule} · {m.confidence:.2f}",
            "detail": f"{_enum(m.decision)} by {m.rule}, confidence {m.confidence:.2f}",
        }})
    for i, m in enumerate(res.other_candidates):
        add(_record(m.left, "excluded"))
        add(_record(m.right, "excluded"))
        els.append({"data": {
            "id": f"cand:{i}", "source": _rid(m.left), "target": _rid(m.right), "kind": "rejected",
            "label": f"{_enum(m.decision).replace('_', ' ')} · {m.confidence:.2f}",
            "detail": f"Excluded: {_enum(m.decision)} by {m.rule}, confidence {m.confidence:.2f}",
        }})
    for i, rel in enumerate(result.relationships):
        node = _record(rel.other, "related")
        if rel.other_display:
            node["data"]["label"] = rel.other_display
        add(node)
        ends = ("entity", _rid(rel.other)) if rel.direction == "outbound" else (_rid(rel.other), "entity")
        els.append({"data": {
            "id": f"rel:{i}", "source": ends[0], "target": ends[1], "kind": "rel",
            "label": rel.relationship,
            "detail": f"{rel.relationship} ({rel.direction}) via "
                      f"{rel.provenance.source_object}.{rel.provenance.source_field}",
        }})
    return els


def ontology_graph(entities: list[dict], disabled: set[str]) -> list[dict]:
    """Entity types, their attributes, and the native source field each
    attribute binds to; relationships connect entity types."""
    els: list[dict] = []
    sources: set[str] = set()
    for e in entities:
        name = e["name"]
        els.append({"data": {"id": f"ent:{name}", "kind": "entity", "label": name,
                             "detail": f"Entity type · {len(e['attributes'])} attributes"}})
        for sid in e["sources"]:
            if sid not in sources:
                sources.add(sid)
                els.append({"data": {
                    "id": f"src:{sid}", "kind": "source", "source": sid, "label": sid,
                    "disabled": sid in disabled,
                    "detail": f"Source system{' · disabled in this workspace' if sid in disabled else ''}",
                }})
        for attr, d in e["attributes"].items():
            aid = f"attr:{name}:{attr}"
            els.append({"data": {
                "id": aid, "kind": "attribute", "label": attr,
                "identifying": bool(d.identifying),
                "detail": f"{name}.{attr} · {_enum(d.type)}"
                          f"{' · identifying' if d.identifying else ''}{' · required' if d.required else ''}",
            }})
            els.append({"data": {"id": f"has:{aid}", "source": f"ent:{name}", "target": aid,
                                 "kind": "has", "label": ""}})
            for sid in e["sources"]:
                b = e["bindings"][sid]
                fb = b.fields.get(attr)
                if fb:
                    els.append({"data": {
                        "id": f"bind:{aid}:{sid}", "source": aid, "target": f"src:{sid}",
                        "kind": "binding", "label": fb.source_field,
                        "detail": f"{name}.{attr} ← {sid}.{b.object}.{fb.source_field}",
                    }})
        for rname, rd in e["relationships"].items():
            els.append({"data": {
                "id": f"rel:{name}:{rname}", "source": f"ent:{name}", "target": f"ent:{rd.target}",
                "kind": "rel", "label": rname,
                "detail": f"{name} —{rname} ({_enum(rd.cardinality)})→ {rd.target}",
            }})
    return els
