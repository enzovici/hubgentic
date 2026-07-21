"""Human-readable lineage tree, used by the demo and explain_lineage."""
from __future__ import annotations

from hubgentic.lineage.model import Provenance, UnifiedEntity


def _prov(p: Provenance) -> str:
    ts = p.fetched_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f"← {p.source}.{p.source_object}[{p.source_key}].{p.source_field} "
        f"@{ts}  rule={p.resolution_rule} conf={p.resolution_confidence:.2f}"
    )


def render_lineage_tree(entity: UnifiedEntity) -> str:
    lines = [
        f"UnifiedEntity {entity.entity_type}  (request {entity.request_id})",
    ]
    field_names = list(entity.fields.keys())
    sections = len(field_names) + (1 if entity.relationships else 0)
    for fi, name in enumerate(field_names):
        last_section = fi == sections - 1
        lines.append(f"{'└─' if last_section else '├─'} {name}")
        stem = "   " if last_section else "│  "
        values = entity.fields[name]
        canonical = entity.canonical.get(name)
        for vi, pv in enumerate(values):
            branch = "└─" if vi == len(values) - 1 else "├─"
            star = "★" if canonical is not None and pv == canonical else " "
            lines.append(f"{stem}{branch} {star} {pv.value!r}  {_prov(pv.provenance)}")
    if entity.relationships:
        lines.append("└─ relationships")
        for ri, rel in enumerate(entity.relationships):
            branch = "└─" if ri == len(entity.relationships) - 1 else "├─"
            if rel.direction == "inbound":
                arrow = f"{rel.other_display or rel.other.source_key} —{rel.relationship}→ this"
            else:
                arrow = f"this —{rel.relationship}→ {rel.other_display or rel.other.source_key}"
            lines.append(f"   {branch} {arrow}  {_prov(rel.provenance)}")
    return "\n".join(lines)
