"""MCP server — the only module that imports mcp.*.

Five tools over stdio; every tool returns a Pydantic model, which FastMCP
serializes as structured content with a generated output schema.
"""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from hubgentic.app import build_orchestrator, find_ontology_path
from hubgentic.federation.orchestrator import EntityNotFoundError
from hubgentic.lineage.model import Provenance, ResolutionExplanation, UnifiedEntity
from hubgentic.lineage.render import render_lineage_tree
from hubgentic.ontology.loader import load_ontology
from hubgentic.ontology.model import AttributeDef, RelationshipDef
from hubgentic.resolution.base import ResolutionResult


class SourceSummary(BaseModel):
    id: str
    kind: str
    description: str | None = None


class EntitySummary(BaseModel):
    name: str
    description: str | None = None
    attributes: list[str]
    relationships: list[str]
    bound_sources: list[str]


class OntologySummary(BaseModel):
    name: str
    version: str
    entities: list[EntitySummary]
    sources: list[SourceSummary]


class BindingDescription(BaseModel):
    source: str
    object: str
    key_fields: list[str]
    fields: dict[str, str]  # ontology attribute -> native field
    relationships: dict[str, str] = Field(default_factory=dict)


class EntityDescription(BaseModel):
    entity_type: str
    description: str | None = None
    attributes: dict[str, AttributeDef]
    relationships: dict[str, RelationshipDef]
    bindings: list[BindingDescription]  # in canonical-merge preference order


class LineageExplanation(BaseModel):
    request_id: str
    entity_type: str
    criteria: dict[str, Any]
    fields: dict[str, list[Provenance]]
    resolution: ResolutionExplanation
    rendered: str  # human-readable lineage tree


mcp = FastMCP(
    "hubgentic",
    instructions=(
        "Vendor-neutral federated semantic catalog for regulated financial "
        "services. Entities are resolved across siloed systems of record at "
        "query time; every returned field carries full provenance (source "
        "system, field, fetch time, resolution rule, confidence). Start with "
        "list_ontology, then get_unified_entity with criteria like "
        '{"national_tax_code": "..."} or {"legal_name": "..."}.'
    ),
)

_ontology_path = find_ontology_path()
_ontology = load_ontology(_ontology_path)
_orchestrator = build_orchestrator(_ontology_path)
_graph = _orchestrator.graph


@mcp.tool()
async def list_ontology() -> OntologySummary:
    """List the ontology: entity types, their attributes/relationships, and
    the federated source systems bound to them."""
    entities = [
        EntitySummary(
            name=name,
            description=_ontology.entities[name].description,
            attributes=list(_graph.attributes_of(name)),
            relationships=list(_graph.relationships_of(name)),
            bound_sources=_graph.sources_for(name),
        )
        for name in _graph.entity_types()
    ]
    sources = [
        SourceSummary(id=sid, kind=sdef.kind, description=sdef.description)
        for sid, sdef in _graph.sources().items()
    ]
    return OntologySummary(
        name=_ontology.meta.name,
        version=_ontology.meta.version,
        entities=entities,
        sources=sources,
    )


@mcp.tool()
async def describe_entity(entity_type: str) -> EntityDescription:
    """Describe one entity type: typed attributes, relationships, and the
    per-source field bindings (in canonical-merge preference order)."""
    try:
        attributes = _graph.attributes_of(entity_type)
    except KeyError:
        raise ValueError(
            f"unknown entity type '{entity_type}'; known: {_graph.entity_types()}"
        )
    bindings = [
        BindingDescription(
            source=source_id,
            object=b.object,
            key_fields=b.key_fields,
            fields={attr: fb.source_field for attr, fb in b.fields.items()},
            relationships={
                rel: rb.source_field for rel, rb in b.relationships.items()
            },
        )
        for source_id in _graph.sources_for(entity_type)
        for b in [_graph.binding_for(entity_type, source_id)]
    ]
    return EntityDescription(
        entity_type=entity_type,
        description=_ontology.entities[entity_type].description,
        attributes=attributes,
        relationships=_graph.relationships_of(entity_type),
        bindings=bindings,
    )


@mcp.tool()
async def resolve_entity(
    entity_type: str, criteria: dict[str, str]
) -> ResolutionResult:
    """Fetch candidate records from all bound sources and run entity
    resolution. Returns clusters, ranked pairwise matches (each with the exact
    rule that fired and its confidence), and unmatched records."""
    try:
        return await _orchestrator.resolve(entity_type, criteria)
    except KeyError as exc:
        raise ValueError(str(exc))


@mcp.tool()
async def get_unified_entity(
    entity_type: str, criteria: dict[str, str]
) -> UnifiedEntity:
    """Resolve one entity across all bound sources and return the unified,
    provenance-annotated view: ALL source values per attribute plus an
    explicitly-policied canonical value. Keep the request_id to call
    explain_lineage."""
    try:
        return await _orchestrator.get_unified(entity_type, criteria)
    except (EntityNotFoundError, KeyError) as exc:
        raise ValueError(str(exc))


@mcp.tool()
async def explain_lineage(
    request_id: str | None = None,
    entity_type: str | None = None,
    criteria: dict[str, str] | None = None,
) -> LineageExplanation:
    """Explain where every field of a unified entity came from. Pass the
    request_id from get_unified_entity (served from a short-lived in-memory
    cache), or entity_type + criteria to recompute."""
    unified: UnifiedEntity | None = None
    if request_id:
        unified = _orchestrator.explain(request_id)
        if unified is None and not (entity_type and criteria):
            raise ValueError(
                f"request_id '{request_id}' not in the explanation cache "
                "(entries expire after 15 minutes); pass entity_type + "
                "criteria to recompute"
            )
    if unified is None:
        if not (entity_type and criteria):
            raise ValueError("pass request_id, or entity_type + criteria")
        try:
            unified = await _orchestrator.get_unified(entity_type, criteria)
        except (EntityNotFoundError, KeyError) as exc:
            raise ValueError(str(exc))
    return LineageExplanation(
        request_id=unified.request_id,
        entity_type=unified.entity_type,
        criteria=unified.criteria,
        fields={
            attr: [pv.provenance for pv in values]
            for attr, values in unified.fields.items()
        },
        resolution=unified.resolution,
        rendered=render_lineage_tree(unified),
    )


def main() -> None:
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
