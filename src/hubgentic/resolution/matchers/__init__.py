from hubgentic.resolution.matchers.deterministic import ExactKeyMatcher
from hubgentic.resolution.matchers.fuzzy import NameDateEmailMatcher
from hubgentic.resolution.matchers.normalized import NormalizedKeyMatcher

__all__ = ["ExactKeyMatcher", "NameDateEmailMatcher", "NormalizedKeyMatcher"]


def default_matchers() -> list:
    """The v0 pipeline, in evaluation order (deterministic → normalized → fuzzy)."""
    return [
        ExactKeyMatcher(attribute="lei", rule_id="deterministic.lei"),
        ExactKeyMatcher(
            attribute="national_tax_code", rule_id="deterministic.tax_code"
        ),
        NormalizedKeyMatcher(
            attribute="lei", normalizer="lei", rule_id="normalized.lei"
        ),
        NormalizedKeyMatcher(
            attribute="national_tax_code",
            normalizer="tax_code",
            rule_id="normalized.tax_code",
        ),
        NameDateEmailMatcher(),
    ]
