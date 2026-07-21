"""Entity-resolution interface — the extension point of hubgentic.

Engine semantics: a CandidateGenerator proposes record pairs (blocking); ordered
Matchers compare each pair; the FIRST decisive result (MATCH, POSSIBLE_MATCH or
NO_MATCH) wins and short-circuits, ABSTAIN falls through to the next matcher.
All-ABSTAIN → unmatched. MATCH edges are clustered (connected components) into
entity clusters. Every result carries the exact rule id and confidence —
auditable by construction. ML matchers drop in by implementing Matcher
(pairwise scoring) or CandidateGenerator (blocking).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class MatchDecision(StrEnum):
    MATCH = "match"                    # decisive: same real-world entity
    POSSIBLE_MATCH = "possible_match"  # above review threshold, below auto-merge
    NO_MATCH = "no_match"              # decisive: NOT the same (e.g. key conflict)
    ABSTAIN = "abstain"                # this matcher cannot judge; fall through


class RecordRef(BaseModel):
    """Stable pointer to one native record in one source system."""

    source: str          # source id from ontology, e.g. "core_banking"
    source_object: str   # native object, e.g. "CIF" / "Account"
    source_key: str      # native primary key value


class CandidateRecord(BaseModel):
    """A source record projected into ontology attribute space via bindings."""

    ref: RecordRef
    entity_type: str                    # e.g. "Counterparty"
    attributes: dict[str, Any]          # ontology attr -> raw value (unnormalized)
    source_fields: dict[str, str]       # ontology attr -> native field (provenance)
    fetched_at: datetime


class MatchEvidence(BaseModel):
    """One attribute-level comparison that contributed to a decision."""

    attribute: str
    left_value: Any
    right_value: Any
    comparator: str                     # e.g. "exact", "normalized_exact", "token_sort_ratio"
    score: float = Field(ge=0.0, le=1.0)


class MatchResult(BaseModel):
    left: RecordRef
    right: RecordRef
    decision: MatchDecision
    confidence: float = Field(ge=0.0, le=1.0)
    rule: str                           # exact rule that fired, e.g. "deterministic.lei"
    evidence: list[MatchEvidence] = Field(default_factory=list)


class ResolutionConfig(BaseModel):
    match_threshold: float = 0.92       # fuzzy score >= this -> MATCH
    possible_threshold: float = 0.75    # in [possible, match) -> POSSIBLE_MATCH
    matcher_ids: list[str] | None = None  # override pipeline subset/order


class Matcher(ABC):
    """Pairwise comparison rule. Deterministic today, ML tomorrow."""

    id: ClassVar[str]                   # e.g. "deterministic.lei"

    @abstractmethod
    def compare(
        self,
        left: CandidateRecord,
        right: CandidateRecord,
        config: ResolutionConfig,
    ) -> MatchResult:
        """Never returns None — return decision=ABSTAIN when unable to judge."""


class CandidateGenerator(ABC):
    """Blocking strategy: which pairs are worth comparing at all."""

    @abstractmethod
    def generate(
        self, records: Sequence[CandidateRecord]
    ) -> Iterable[tuple[CandidateRecord, CandidateRecord]]: ...


class EntityCluster(BaseModel):
    """Records resolved to one real-world entity + the edges that justify it."""

    records: list[RecordRef]
    supporting_matches: list[MatchResult]


class ResolutionResult(BaseModel):
    clusters: list[EntityCluster]
    matches: list[MatchResult]          # all non-ABSTAIN outcomes, confidence-ranked
    unmatched: list[RecordRef]


class ResolutionEngine(ABC):
    @abstractmethod
    def resolve(
        self,
        records: Sequence[CandidateRecord],
        config: ResolutionConfig | None = None,
    ) -> ResolutionResult: ...
