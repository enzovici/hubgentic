"""Deterministic shared-key matcher: raw equality on an identifying attribute.

Raw inequality is NOT decisive here — the values may just be dirty; the
NormalizedKeyMatcher downstream rules on true key conflicts.
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


def _present(value: object) -> bool:
    return value is not None and str(value).strip() != ""


def abstain(left: CandidateRecord, right: CandidateRecord, rule: str) -> MatchResult:
    return MatchResult(
        left=left.ref,
        right=right.ref,
        decision=MatchDecision.ABSTAIN,
        confidence=0.0,
        rule=rule,
    )


class ExactKeyMatcher(Matcher):
    def __init__(self, attribute: str, rule_id: str, confidence: float = 1.0) -> None:
        self.id = rule_id
        self.attribute = attribute
        self.confidence = confidence

    def compare(
        self,
        left: CandidateRecord,
        right: CandidateRecord,
        config: ResolutionConfig,
    ) -> MatchResult:
        lv = left.attributes.get(self.attribute)
        rv = right.attributes.get(self.attribute)
        if not (_present(lv) and _present(rv)):
            return abstain(left, right, self.id)
        if str(lv).strip() == str(rv).strip():
            return MatchResult(
                left=left.ref,
                right=right.ref,
                decision=MatchDecision.MATCH,
                confidence=self.confidence,
                rule=self.id,
                evidence=[
                    MatchEvidence(
                        attribute=self.attribute,
                        left_value=lv,
                        right_value=rv,
                        comparator="exact",
                        score=1.0,
                    )
                ],
            )
        return abstain(left, right, self.id)
