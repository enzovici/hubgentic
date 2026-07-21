"""Probabilistic matcher on name + date-of-birth/incorporation + email.

Weighted comparison of available signals; weights renormalize over the signals
both records actually carry. Thresholds come from ResolutionConfig, so they are
tunable per request. Score bands: >= match_threshold → MATCH,
>= possible_threshold → POSSIBLE_MATCH, else NO_MATCH (this matcher runs last
in the default pipeline, so a low score is a judgment, not an abstention).
"""
from __future__ import annotations

from rapidfuzz import fuzz

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

_NAME_WEIGHT = 0.5
_DATE_WEIGHT = 0.3
_EMAIL_WEIGHT = 0.2


def _iso_date(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip()[:10]
    return s or None


class NameDateEmailMatcher(Matcher):
    id = "fuzzy.name_dob_email"

    def compare(
        self,
        left: CandidateRecord,
        right: CandidateRecord,
        config: ResolutionConfig,
    ) -> MatchResult:
        ln = normalize("person_or_org_name", left.attributes.get("legal_name"))
        rn = normalize("person_or_org_name", right.attributes.get("legal_name"))
        if ln is None or rn is None:
            return abstain(left, right, self.id)

        lp = left.attributes.get("party_type")
        rp = right.attributes.get("party_type")
        if lp and rp and lp != rp:
            # An individual and a legal entity cannot be the same counterparty.
            return MatchResult(
                left=left.ref,
                right=right.ref,
                decision=MatchDecision.NO_MATCH,
                confidence=0.9,
                rule=self.id,
                evidence=[
                    MatchEvidence(
                        attribute="party_type",
                        left_value=lp,
                        right_value=rp,
                        comparator="party_type_conflict",
                        score=0.0,
                    )
                ],
            )

        name_score = fuzz.token_sort_ratio(ln, rn) / 100.0
        evidence = [
            MatchEvidence(
                attribute="legal_name",
                left_value=left.attributes.get("legal_name"),
                right_value=right.attributes.get("legal_name"),
                comparator="token_sort_ratio",
                score=name_score,
            )
        ]
        components: list[tuple[float, float]] = [(_NAME_WEIGHT, name_score)]

        for attr in ("date_of_birth", "incorporation_date"):
            ld, rd = _iso_date(left.attributes.get(attr)), _iso_date(
                right.attributes.get(attr)
            )
            if ld and rd:
                date_score = 1.0 if ld == rd else 0.0
                components.append((_DATE_WEIGHT, date_score))
                evidence.append(
                    MatchEvidence(
                        attribute=attr,
                        left_value=ld,
                        right_value=rd,
                        comparator="exact",
                        score=date_score,
                    )
                )
                break

        le = normalize("email", left.attributes.get("email"))
        re_ = normalize("email", right.attributes.get("email"))
        if le and re_:
            email_score = 1.0 if le == re_ else 0.0
            components.append((_EMAIL_WEIGHT, email_score))
            evidence.append(
                MatchEvidence(
                    attribute="email",
                    left_value=left.attributes.get("email"),
                    right_value=right.attributes.get("email"),
                    comparator="normalized_exact",
                    score=email_score,
                )
            )

        total_weight = sum(w for w, _ in components)
        score = sum(w * s for w, s in components) / total_weight

        if score >= config.match_threshold:
            decision, confidence = MatchDecision.MATCH, score
        elif score >= config.possible_threshold:
            decision, confidence = MatchDecision.POSSIBLE_MATCH, score
        else:
            decision, confidence = MatchDecision.NO_MATCH, 1.0 - score

        return MatchResult(
            left=left.ref,
            right=right.ref,
            decision=decision,
            confidence=confidence,
            rule=self.id,
            evidence=evidence,
        )
