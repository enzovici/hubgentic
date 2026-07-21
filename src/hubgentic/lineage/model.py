"""Provenance-annotated output models — lineage is part of the data contract.

Neutrality invariant: `fields` always carries EVERY source's value with full
provenance; `canonical` is an additional, explicitly-policied selection (v0:
first non-null in the ontology's binding order), never a silent replacement.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from hubgentic.resolution.base import MatchResult, RecordRef


class Provenance(BaseModel):
    source: str                 # source system id, e.g. "core_banking"
    source_object: str          # native object, e.g. "CIF"
    source_key: str             # native record key
    source_field: str           # native field the value came from
    fetched_at: datetime        # when the value was fetched (request-scoped)
    resolution_rule: str        # rule that joined this record into the entity
    resolution_confidence: float


class ProvenancedValue(BaseModel):
    value: Any
    provenance: Provenance


class ResolutionExplanation(BaseModel):
    cluster_records: list[RecordRef]
    supporting_matches: list[MatchResult]
    other_candidates: list[MatchResult] = Field(default_factory=list)
    sources_consulted: list[str]
    sources_denied: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RelationshipAssertion(BaseModel):
    relationship: str
    direction: Literal["outbound", "inbound"]
    other: RecordRef
    other_display: str | None = None
    provenance: Provenance


class UnifiedEntity(BaseModel):
    request_id: str
    entity_type: str
    criteria: dict[str, Any]
    fields: dict[str, list[ProvenancedValue]]
    canonical: dict[str, ProvenancedValue]
    relationships: list[RelationshipAssertion] = Field(default_factory=list)
    resolution: ResolutionExplanation
    generated_at: datetime
