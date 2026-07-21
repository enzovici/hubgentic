"""Normalized deterministic matcher: equality after canonicalization.

Unlike the raw ExactKeyMatcher, a normalized inequality IS decisive: two
records bearing different canonical identifying keys are different entities
(NO_MATCH short-circuits the pipeline — this is what defeats homonym traps).
"""
from __future__ import annotations

from hubgentic.resolution.base import (
    CandidateRecord,
    Matcher,
    MatchDecision,
    MatchEvidence,
    MatchResult,
    ResolutionConfig,
)
from hubgentic.resolution.matchers.deterministic import abstain
from hubgentic.resolution.normalize import normalize


class NormalizedKeyMatcher(Matcher):
    def __init__(
        self,
        attribute: str,
        normalizer: str,
        rule_id: str,
        match_confidence: float = 0.98,
        conflict_confidence: float = 0.95,
    ) -> None:
        self.id = rule_id
        self.attribute = attribute
        self.normalizer = normalizer
        self.match_confidence = match_confidence
        self.conflict_confidence = conflict_confidence

    def compare(
        self,
        left: CandidateRecord,
        right: CandidateRecord,
        config: ResolutionConfig,
    ) -> MatchResult:
        ln = normalize(self.normalizer, left.attributes.get(self.attribute))
        rn = normalize(self.normalizer, right.attributes.get(self.attribute))
        if ln is None or rn is None:
            return abstain(left, right, self.id)
        equal = ln == rn
        evidence = [
            MatchEvidence(
                attribute=self.attribute,
                left_value=left.attributes.get(self.attribute),
                right_value=right.attributes.get(self.attribute),
                comparator="normalized_exact",
                score=1.0 if equal else 0.0,
            )
        ]
        if equal:
            return MatchResult(
                left=left.ref,
                right=right.ref,
                decision=MatchDecision.MATCH,
                confidence=self.match_confidence,
                rule=self.id,
                evidence=evidence,
            )
        return MatchResult(
            left=left.ref,
            right=right.ref,
            decision=MatchDecision.NO_MATCH,
            confidence=self.conflict_confidence,
            rule=self.id,
            evidence=evidence,
        )
