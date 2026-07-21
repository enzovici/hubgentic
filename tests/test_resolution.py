"""Resolution engine scenarios — the acceptance criteria of v0.

Synthetic CandidateRecords, engine assembled from the default pipeline:
deterministic.lei → deterministic.tax_code → normalized.lei →
normalized.tax_code → fuzzy.name_dob_email.
"""
from datetime import UTC, datetime

import pytest

from hubgentic.resolution.base import (
    CandidateRecord,
    MatchDecision,
    RecordRef,
    ResolutionConfig,
)
from hubgentic.resolution.engine import PipelineResolutionEngine
from hubgentic.resolution.matchers import default_matchers


def cand(source: str, key: str, **attributes) -> CandidateRecord:
    return CandidateRecord(
        ref=RecordRef(source=source, source_object="T", source_key=key),
        entity_type="Counterparty",
        attributes=attributes,
        source_fields={attr: attr.upper() for attr in attributes},
        fetched_at=datetime.now(UTC),
    )


@pytest.fixture
def engine():
    return PipelineResolutionEngine(default_matchers())


def test_clean_lei_match(engine):
    a = cand("core_banking", "1", legal_name="ACME SPA", lei="529900ACME000000IT01")
    b = cand("kyc", "2", legal_name="Acme Industries", lei="529900ACME000000IT01")
    result = engine.resolve([a, b])
    assert len(result.clusters) == 1
    [match] = result.clusters[0].supporting_matches
    assert match.rule == "deterministic.lei"
    assert match.confidence == 1.0
    assert match.decision == MatchDecision.MATCH


def test_clean_tax_code_match(engine):
    a = cand("core_banking", "1", legal_name="ROSSI MARIO", national_tax_code="RSSMRA80A01H501U")
    b = cand("crm", "2", legal_name="Mario Rossi", national_tax_code="RSSMRA80A01H501U")
    result = engine.resolve([a, b])
    [match] = result.clusters[0].supporting_matches
    assert match.rule == "deterministic.tax_code"


def test_dirty_tax_code_matches_via_normalization(engine):
    a = cand("core_banking", "1", legal_name="ROSSI MARIO", national_tax_code="RSSMRA80A01H501U")
    b = cand("crm", "2", legal_name="Mario Rossi", national_tax_code=" rssmra80a01h501u ")
    result = engine.resolve([a, b])
    assert len(result.clusters) == 1
    [match] = result.clusters[0].supporting_matches
    assert match.rule == "normalized.tax_code"
    assert match.decision == MatchDecision.MATCH
    assert match.confidence == pytest.approx(0.98)


def test_key_conflict_defeats_homonym_trap(engine):
    """Identical names, same DOB — but conflicting tax codes. The normalized
    key conflict must short-circuit to NO_MATCH before fuzzy ever runs."""
    a = cand(
        "core_banking", "1",
        legal_name="ROSSI MARIO", national_tax_code="RSSMRA80A01H501U",
        date_of_birth="1980-01-01",
    )
    b = cand(
        "crm", "2",
        legal_name="Mario Rossi", national_tax_code="RSSMRA80A01F205Z",
        date_of_birth="1980-01-01",
    )
    result = engine.resolve([a, b])
    assert result.clusters == []
    assert len(result.unmatched) == 2
    [match] = result.matches
    assert match.decision == MatchDecision.NO_MATCH
    assert match.rule == "normalized.tax_code"  # fuzzy never fired


def test_fuzzy_match_without_shared_key(engine):
    a = cand(
        "core_banking", "1",
        legal_name="BIANCHI LUCIA", national_tax_code="BNCLCU85M41F205X",
        date_of_birth="1985-08-01", email="lucia.bianchi@gmail.com",
        party_type="individual",
    )
    b = cand(
        "crm", "2",
        legal_name="Lucia Bianchi",  # no tax code at all
        date_of_birth="1985-08-01", email="Lucia.Bianchi@GMAIL.com",
        party_type="individual",
    )
    result = engine.resolve([a, b])
    assert len(result.clusters) == 1
    [match] = result.clusters[0].supporting_matches
    assert match.rule == "fuzzy.name_dob_email"
    assert match.confidence >= 0.92
    comparators = {e.comparator for e in match.evidence}
    assert "token_sort_ratio" in comparators


def test_fuzzy_sibling_stays_no_match(engine):
    """Similar names, different DOB and email — true negative."""
    a = cand(
        "core_banking", "1",
        legal_name="ROSSI MARIA", date_of_birth="1982-03-05",
        email="maria.rossi@libero.it",
    )
    b = cand(
        "crm", "2",
        legal_name="Mario Rossi", date_of_birth="1980-01-01",
        email="mrossi80@gmail.com",
    )
    result = engine.resolve([a, b])
    assert result.clusters == []
    [match] = result.matches
    assert match.decision == MatchDecision.NO_MATCH
    assert match.rule == "fuzzy.name_dob_email"


def test_possible_match_band(engine):
    """Same name + DOB, different email, no keys → POSSIBLE_MATCH, no merge."""
    a = cand(
        "core_banking", "1",
        legal_name="VERDI GIUSEPPE", date_of_birth="1975-04-22",
        email="g.verdi@verdi-consulting.it",
    )
    b = cand(
        "crm", "2",
        legal_name="Giuseppe Verdi", date_of_birth="1975-04-22",
        email="giuseppe@verdiconsulting.com",
    )
    result = engine.resolve([a, b])
    assert result.clusters == []
    [match] = result.matches
    assert match.decision == MatchDecision.POSSIBLE_MATCH
    assert 0.75 <= match.confidence < 0.92


def test_party_type_conflict_is_no_match(engine):
    a = cand("core_banking", "1", legal_name="AURORA", party_type="legal_entity")
    b = cand("crm", "2", legal_name="Aurora", party_type="individual")
    [match] = engine.resolve([a, b]).matches
    assert match.decision == MatchDecision.NO_MATCH
    assert match.evidence[0].comparator == "party_type_conflict"


def test_near_duplicates_cluster_across_and_within_sources(engine):
    cb = cand(
        "core_banking", "CIF-1004",
        legal_name="FERRARI LOGISTICS S.R.L.", national_tax_code="IT09876543210",
        email="info@ferrarilogistics.it", incorporation_date="2005-11-03",
    )
    crm1 = cand(
        "crm", "001A000004",
        legal_name="Ferrari Logistics SRL", national_tax_code="IT09876543210",
        email="info@ferrarilogistics.it",
    )
    crm2 = cand(  # near-duplicate inside the CRM: typo, no tax code
        "crm", "001A000005",
        legal_name="Ferrari Logistcs S.r.l.", email="info@ferrarilogistics.it",
    )
    result = engine.resolve([cb, crm1, crm2])
    assert len(result.clusters) == 1
    assert len(result.clusters[0].records) == 3
    rules = {m.rule for m in result.clusters[0].supporting_matches}
    assert "deterministic.tax_code" in rules  # cb ↔ crm1
    assert "fuzzy.name_dob_email" in rules    # crm2 joined fuzzily


def test_true_negatives_stay_unmatched(engine):
    a = cand("core_banking", "1", legal_name="TIRRENIA SHIPPING S.P.A.",
             national_tax_code="IT06666777880")
    b = cand("crm", "2", legal_name="Delta Consulting Group",
             email="contact@deltacg.com")
    result = engine.resolve([a, b])
    assert result.clusters == []
    assert len(result.unmatched) == 2


def test_all_abstain_when_nothing_comparable(engine):
    a = cand("core_banking", "1", legal_name="ACME SPA")
    b = cand("crm", "2", email="hello@startupxyz.io")  # no name, no keys
    result = engine.resolve([a, b])
    assert result.matches == []
    assert len(result.unmatched) == 2


def test_matcher_subset_and_order_override(engine):
    a = cand("core_banking", "1", legal_name="ACME SPA", lei="529900ACME000000IT01")
    b = cand("crm", "2", legal_name="Totally Different", lei="529900ACME000000IT01")
    fuzzy_only = ResolutionConfig(matcher_ids=["fuzzy.name_dob_email"])
    result = engine.resolve([a, b], fuzzy_only)
    assert result.clusters == []  # LEI matcher excluded, names don't correlate

    with pytest.raises(ValueError, match="unknown matcher ids"):
        engine.resolve([a, b], ResolutionConfig(matcher_ids=["ml.embedding"]))


def test_thresholds_are_configurable(engine):
    a = cand("core_banking", "1", legal_name="VERDI GIUSEPPE",
             date_of_birth="1975-04-22", email="a@x.it")
    b = cand("crm", "2", legal_name="Giuseppe Verdi",
             date_of_birth="1975-04-22", email="b@y.com")
    lenient = ResolutionConfig(match_threshold=0.8)
    result = engine.resolve([a, b], lenient)
    assert len(result.clusters) == 1  # 0.8 score now clears the bar
