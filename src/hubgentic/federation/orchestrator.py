"""Federation orchestrator: bindings → concurrent fetch → resolution → merge.

Correlation is ephemeral and request-scoped; the orchestrator holds nothing at
rest beyond a TTL-bounded in-memory explanation cache. It depends only on the
OntologyGraph, SourceAdapter, GovernancePolicy and ResolutionEngine interfaces,
so every implementation behind them is swappable.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import anyio

from hubgentic.governance.policy import FetchRequest, GovernancePolicy
from hubgentic.lineage.model import (
    Provenance,
    ProvenancedValue,
    RelationshipAssertion,
    ResolutionExplanation,
    UnifiedEntity,
)
from hubgentic.ontology.graph import OntologyGraph
from hubgentic.ontology.model import SourceBinding
from hubgentic.resolution.base import (
    CandidateRecord,
    MatchDecision,
    RecordRef,
    ResolutionConfig,
    ResolutionEngine,
    ResolutionResult,
)
from hubgentic.resolution.normalize import NORMALIZERS
from hubgentic.federation.cache import RequestCache
from hubgentic.sources.base import SourceAdapter, SourceRecord

_SINGLETON_RULE = "resolution.singleton"


class EntityNotFoundError(LookupError):
    pass


def _ref_key(ref: RecordRef) -> tuple[str, str, str]:
    return (ref.source, ref.source_object, ref.source_key)


class FederationOrchestrator:
    def __init__(
        self,
        graph: OntologyGraph,
        adapters: dict[str, SourceAdapter],
        policy: GovernancePolicy,
        engine: ResolutionEngine,
        cache_ttl_s: float = 900.0,
    ) -> None:
        self._graph = graph
        self._adapters = adapters
        self._policy = policy
        self._engine = engine
        self._cache = RequestCache(cache_ttl_s)

    @property
    def graph(self) -> OntologyGraph:
        return self._graph

    # ── fetch ────────────────────────────────────────────────────────────

    async def fetch_candidates(
        self, entity_type: str, criteria: dict[str, Any]
    ) -> tuple[
        list[CandidateRecord],
        list[str],
        list[tuple[str, str]],
        dict[tuple[str, str, str], SourceRecord],
    ]:
        sources = self._graph.sources_for(entity_type)
        if not sources:
            raise KeyError(f"entity '{entity_type}' has no source bindings")

        consulted: list[str] = []
        denied: list[tuple[str, str]] = []
        results: dict[str, list[SourceRecord]] = {}

        async def fetch(source_id: str) -> None:
            results[source_id] = await self._adapters[source_id].search(
                entity_type, criteria
            )

        async with anyio.create_task_group() as tg:
            for source_id in sources:
                decision = self._policy.check(
                    FetchRequest(
                        source=source_id, entity_type=entity_type, criteria=criteria
                    )
                )
                if not decision.allowed:
                    denied.append((source_id, decision.reason))
                    continue
                consulted.append(source_id)
                tg.start_soon(fetch, source_id)

        candidates: list[CandidateRecord] = []
        native: dict[tuple[str, str, str], SourceRecord] = {}
        for source_id in consulted:
            binding = self._graph.binding_for(entity_type, source_id)
            for record in results.get(source_id, []):
                candidate = self._project(entity_type, binding, record)
                candidates.append(candidate)
                native[_ref_key(candidate.ref)] = record
        return candidates, consulted, denied, native

    @staticmethod
    def _project(
        entity_type: str, binding: SourceBinding, record: SourceRecord
    ) -> CandidateRecord:
        attributes = {
            attr: fb.to_ontology_value(record.fields.get(fb.source_field))
            for attr, fb in binding.fields.items()
        }
        source_fields = {attr: fb.source_field for attr, fb in binding.fields.items()}
        return CandidateRecord(
            ref=RecordRef(
                source=record.source,
                source_object=record.object,
                source_key=record.key,
            ),
            entity_type=entity_type,
            attributes=attributes,
            source_fields=source_fields,
            fetched_at=record.fetched_at,
        )

    # ── resolve ──────────────────────────────────────────────────────────

    async def resolve(
        self,
        entity_type: str,
        criteria: dict[str, Any],
        config: ResolutionConfig | None = None,
    ) -> ResolutionResult:
        candidates, _, _, _ = await self.fetch_candidates(entity_type, criteria)
        return self._engine.resolve(candidates, config)

    # ── unify ────────────────────────────────────────────────────────────

    async def get_unified(
        self,
        entity_type: str,
        criteria: dict[str, Any],
        config: ResolutionConfig | None = None,
    ) -> UnifiedEntity:
        candidates, consulted, denied, native = await self.fetch_candidates(
            entity_type, criteria
        )
        if not candidates:
            raise EntityNotFoundError(
                f"no candidate records for {entity_type} matching {criteria} "
                f"in sources {consulted}"
            )
        resolution = self._engine.resolve(candidates, config)
        by_key = {_ref_key(c.ref): c for c in candidates}

        cluster_refs, supporting = self._pick_unit(
            entity_type, criteria, resolution, by_key
        )
        source_order = {
            sid: i for i, sid in enumerate(self._graph.sources_for(entity_type))
        }
        members = sorted(
            (by_key[_ref_key(ref)] for ref in cluster_refs),
            key=lambda c: (source_order[c.ref.source], c.ref.source_key),
        )

        rule_by_record = self._rules_per_record(cluster_refs, supporting)

        fields: dict[str, list[ProvenancedValue]] = {}
        for attr in self._graph.attributes_of(entity_type):
            for cand in members:
                value = cand.attributes.get(attr)
                if value is None:
                    continue
                rule, conf = rule_by_record[_ref_key(cand.ref)]
                fields.setdefault(attr, []).append(
                    ProvenancedValue(
                        value=value,
                        provenance=Provenance(
                            source=cand.ref.source,
                            source_object=cand.ref.source_object,
                            source_key=cand.ref.source_key,
                            source_field=cand.source_fields[attr],
                            fetched_at=cand.fetched_at,
                            resolution_rule=rule,
                            resolution_confidence=conf,
                        ),
                    )
                )
        # Canonical policy: members are sorted in binding order, so the first
        # collected value per attribute IS "first non-null in binding order".
        canonical = {attr: values[0] for attr, values in fields.items()}

        relationships = await self._expand_relationships(
            entity_type, members, native, rule_by_record
        )

        member_keys = {_ref_key(ref) for ref in cluster_refs}
        other_candidates = [
            m
            for m in resolution.matches
            if m.decision != MatchDecision.MATCH
            and (_ref_key(m.left) in member_keys or _ref_key(m.right) in member_keys)
        ]
        notes = [
            "canonical = first non-null value in ontology binding order "
            "(explicit merge policy; all source values retained above)",
        ]
        if any(m.decision == MatchDecision.POSSIBLE_MATCH for m in other_candidates):
            notes.append(
                "possible matches below the auto-merge threshold were excluded "
                "from this entity; see resolution.other_candidates"
            )

        unified = UnifiedEntity(
            request_id=uuid.uuid4().hex[:12],
            entity_type=entity_type,
            criteria=dict(criteria),
            fields=fields,
            canonical=canonical,
            relationships=relationships,
            resolution=ResolutionExplanation(
                cluster_records=list(cluster_refs),
                supporting_matches=supporting,
                other_candidates=other_candidates,
                sources_consulted=consulted,
                sources_denied=[f"{sid}: {reason}" for sid, reason in denied],
                notes=notes,
            ),
            generated_at=datetime.now(UTC),
        )
        self._cache.put(unified.request_id, unified)
        return unified

    def explain(self, request_id: str) -> UnifiedEntity | None:
        return self._cache.get(request_id)

    # ── internals ────────────────────────────────────────────────────────

    def _pick_unit(
        self,
        entity_type: str,
        criteria: dict[str, Any],
        resolution: ResolutionResult,
        by_key: dict[tuple[str, str, str], CandidateRecord],
    ) -> tuple[list[RecordRef], list]:
        """Choose the cluster (or singleton) the request is about: most
        criteria-satisfying members, then largest, then earliest source."""
        units: list[tuple[list[RecordRef], list]] = [
            (c.records, c.supporting_matches) for c in resolution.clusters
        ] + [([ref], []) for ref in resolution.unmatched]

        source_order = {
            sid: i for i, sid in enumerate(self._graph.sources_for(entity_type))
        }
        attributes = self._graph.attributes_of(entity_type)

        def crit_hits(refs: list[RecordRef]) -> int:
            return sum(
                1
                for ref in refs
                if self._matches_criteria(by_key[_ref_key(ref)], criteria, attributes)
            )

        def rank(unit: tuple[list[RecordRef], list]) -> tuple[int, int, int]:
            refs, _ = unit
            return (
                -crit_hits(refs),
                -len(refs),
                min(source_order.get(ref.source, 99) for ref in refs),
            )

        best = min(units, key=rank)
        return best

    @staticmethod
    def _matches_criteria(
        candidate: CandidateRecord, criteria: dict[str, Any], attributes: dict
    ) -> bool:
        for attr, wanted in criteria.items():
            value = candidate.attributes.get(attr)
            if value is None:
                return False
            attr_def = attributes.get(attr)
            if attr == "legal_name":
                norm = NORMALIZERS["person_or_org_name"]
                q, s = norm(wanted), norm(value)
                if q is None or s is None or not set(q.split()) <= set(s.split()):
                    return False
            elif attr_def is not None and attr_def.normalizer:
                norm = NORMALIZERS[attr_def.normalizer]
                if norm(wanted) != norm(value):
                    return False
            elif str(wanted).strip() != str(value).strip():
                return False
        return True

    @staticmethod
    def _rules_per_record(
        cluster_refs: list[RecordRef], supporting: list
    ) -> dict[tuple[str, str, str], tuple[str, float]]:
        rules: dict[tuple[str, str, str], tuple[str, float]] = {
            _ref_key(ref): (_SINGLETON_RULE, 1.0) for ref in cluster_refs
        }
        for match in supporting:
            for endpoint in (match.left, match.right):
                key = _ref_key(endpoint)
                current = rules.get(key)
                if (
                    current is None
                    or current[0] == _SINGLETON_RULE
                    or match.confidence > current[1]
                ):
                    rules[key] = (match.rule, match.confidence)
        return rules

    async def _expand_relationships(
        self,
        entity_type: str,
        members: list[CandidateRecord],
        native: dict[tuple[str, str, str], SourceRecord],
        rule_by_record: dict[tuple[str, str, str], tuple[str, float]],
    ) -> list[RelationshipAssertion]:
        assertions: list[RelationshipAssertion] = []
        for cand in members:
            binding = self._graph.binding_for(entity_type, cand.ref.source)
            record = native[_ref_key(cand.ref)]
            for rel_name, rel_binding in binding.relationships.items():
                ref_value = record.fields.get(rel_binding.source_field)
                if ref_value is None:
                    continue
                decision = self._policy.check(
                    FetchRequest(
                        source=cand.ref.source,
                        entity_type=entity_type,
                        criteria={rel_binding.references: ref_value},
                        purpose="relationship_expansion",
                    )
                )
                if not decision.allowed:
                    continue
                other = await self._adapters[cand.ref.source].get(
                    entity_type, str(ref_value)
                )
                if other is None:
                    continue
                projected = self._project(entity_type, binding, other)
                rule, conf = rule_by_record[_ref_key(cand.ref)]
                assertions.append(
                    RelationshipAssertion(
                        relationship=rel_name,
                        direction=rel_binding.direction,
                        other=projected.ref,
                        other_display=projected.attributes.get("legal_name"),
                        provenance=Provenance(
                            source=cand.ref.source,
                            source_object=cand.ref.source_object,
                            source_key=cand.ref.source_key,
                            source_field=rel_binding.source_field,
                            fetched_at=other.fetched_at,
                            resolution_rule=rule,
                            resolution_confidence=conf,
                        ),
                    )
                )
        return assertions
