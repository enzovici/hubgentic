"""Pipeline resolution engine: ordered matchers, short-circuit, clustering."""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from hubgentic.resolution.base import (
    CandidateGenerator,
    CandidateRecord,
    EntityCluster,
    Matcher,
    MatchDecision,
    MatchResult,
    RecordRef,
    ResolutionConfig,
    ResolutionEngine,
    ResolutionResult,
)

_DECISION_RANK = {
    MatchDecision.MATCH: 0,
    MatchDecision.POSSIBLE_MATCH: 1,
    MatchDecision.NO_MATCH: 2,
}


def _ref_key(ref: RecordRef) -> tuple[str, str, str]:
    return (ref.source, ref.source_object, ref.source_key)


class AllPairsGenerator(CandidateGenerator):
    """Compare every unordered pair — including same-source pairs, so
    near-duplicates inside one silo cluster too. Fine at v0 scale; real
    blocking strategies replace this class, not the engine."""

    def generate(
        self, records: Sequence[CandidateRecord]
    ) -> Iterable[tuple[CandidateRecord, CandidateRecord]]:
        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                yield records[i], records[j]


class PipelineResolutionEngine(ResolutionEngine):
    def __init__(
        self,
        matchers: Sequence[Matcher],
        generator: CandidateGenerator | None = None,
    ) -> None:
        self._matchers = list(matchers)
        self._generator = generator or AllPairsGenerator()

    def resolve(
        self,
        records: Sequence[CandidateRecord],
        config: ResolutionConfig | None = None,
    ) -> ResolutionResult:
        config = config or ResolutionConfig()
        matchers = self._select_matchers(config)

        outcomes: list[MatchResult] = []
        for left, right in self._generator.generate(records):
            for matcher in matchers:
                result = matcher.compare(left, right, config)
                if result.decision != MatchDecision.ABSTAIN:
                    outcomes.append(result)
                    break

        clusters, unmatched = self._cluster(records, outcomes)
        outcomes.sort(key=lambda m: (_DECISION_RANK[m.decision], -m.confidence))
        return ResolutionResult(
            clusters=clusters, matches=outcomes, unmatched=unmatched
        )

    def _select_matchers(self, config: ResolutionConfig) -> list[Matcher]:
        if config.matcher_ids is None:
            return self._matchers
        by_id = {m.id: m for m in self._matchers}
        unknown = [mid for mid in config.matcher_ids if mid not in by_id]
        if unknown:
            raise ValueError(
                f"unknown matcher ids {unknown}; available: {sorted(by_id)}"
            )
        return [by_id[mid] for mid in config.matcher_ids]

    @staticmethod
    def _cluster(
        records: Sequence[CandidateRecord], outcomes: list[MatchResult]
    ) -> tuple[list[EntityCluster], list[RecordRef]]:
        # Union-find over MATCH edges; connected components become clusters.
        parent: dict[tuple[str, str, str], tuple[str, str, str]] = {
            _ref_key(r.ref): _ref_key(r.ref) for r in records
        }

        def find(k: tuple[str, str, str]) -> tuple[str, str, str]:
            while parent[k] != k:
                parent[k] = parent[parent[k]]
                k = parent[k]
            return k

        for m in outcomes:
            if m.decision == MatchDecision.MATCH:
                lk, rk = find(_ref_key(m.left)), find(_ref_key(m.right))
                if lk != rk:
                    parent[rk] = lk

        groups: dict[tuple[str, str, str], list[RecordRef]] = {}
        for record in records:
            groups.setdefault(find(_ref_key(record.ref)), []).append(record.ref)

        clusters: list[EntityCluster] = []
        unmatched: list[RecordRef] = []
        for members in groups.values():
            if len(members) == 1:
                unmatched.append(members[0])
                continue
            member_keys = {_ref_key(ref) for ref in members}
            supporting = [
                m
                for m in outcomes
                if m.decision == MatchDecision.MATCH
                and _ref_key(m.left) in member_keys
                and _ref_key(m.right) in member_keys
            ]
            clusters.append(
                EntityCluster(records=members, supporting_matches=supporting)
            )
        clusters.sort(key=lambda c: -len(c.records))
        return clusters, unmatched
