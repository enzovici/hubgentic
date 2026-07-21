"""Federation orchestrator: concurrent fetch, governance on every fetch,
neutral merge with complete provenance, ephemeral explanation cache."""
import time

import pytest

from hubgentic.app import build_orchestrator
from hubgentic.federation.orchestrator import (
    EntityNotFoundError,
    FederationOrchestrator,
)
from hubgentic.governance.policy import (
    AllowAllPolicy,
    FetchRequest,
    GovernancePolicy,
    PolicyDecision,
)
from hubgentic.resolution.base import MatchDecision
from hubgentic.sources.base import SourceAdapter
from hubgentic.sources.mock_crm import MockCrmAdapter

ACME_TAX = {"national_tax_code": "IT01234567890"}


async def test_acme_unified_across_both_silos(orchestrator):
    unified = await orchestrator.get_unified("Counterparty", ACME_TAX)

    refs = unified.resolution.cluster_records
    assert {r.source for r in refs} == {"core_banking", "crm"}
    [match] = unified.resolution.supporting_matches
    assert match.rule == "deterministic.tax_code"

    # neutral merge: ALL values retained, canonical is explicit binding order
    names = unified.fields["legal_name"]
    assert {pv.value for pv in names} == {
        "ACME INDUSTRIES S.P.A.",
        "Acme Industries SpA",
    }
    assert unified.canonical["legal_name"].value == "ACME INDUSTRIES S.P.A."
    assert unified.canonical["legal_name"].provenance.source == "core_banking"

    # every field value carries complete provenance
    for values in unified.fields.values():
        for pv in values:
            p = pv.provenance
            assert p.source and p.source_object and p.source_key and p.source_field
            assert p.fetched_at.tzinfo is not None
            assert p.resolution_rule
            assert 0.0 <= p.resolution_confidence <= 1.0


async def test_lei_present_only_where_bound(orchestrator):
    unified = await orchestrator.get_unified("Counterparty", ACME_TAX)
    [lei] = unified.fields["lei"]  # CRM has no LEI binding — one value only
    assert lei.provenance.source == "core_banking"
    assert lei.provenance.source_field == "LEI_CODE"


async def test_acme_beneficial_owner_relationship(orchestrator):
    unified = await orchestrator.get_unified("Counterparty", ACME_TAX)
    [rel] = unified.relationships
    assert rel.relationship == "controls"
    assert rel.direction == "inbound"
    assert rel.other_display == "GREENFIELD CAPITAL HOLDING S.P.A."
    assert rel.provenance.source_field == "CONTROLLING_CIF_ID"


async def test_lucia_fuzzy_unification_no_shared_key(orchestrator):
    unified = await orchestrator.get_unified(
        "Counterparty", {"legal_name": "Lucia Bianchi"}
    )
    refs = unified.resolution.cluster_records
    assert {r.source for r in refs} == {"core_banking", "crm"}
    [match] = unified.resolution.supporting_matches
    assert match.rule == "fuzzy.name_dob_email"
    # tax code exists only in core banking; provenance shows the joining rule
    [tax] = unified.fields["national_tax_code"]
    assert tax.value == "BNCLCU85M41F205X"
    assert tax.provenance.resolution_rule == "fuzzy.name_dob_email"


async def test_verdi_possible_match_not_merged(orchestrator):
    unified = await orchestrator.get_unified(
        "Counterparty", {"legal_name": "Giuseppe Verdi"}
    )
    assert len(unified.resolution.cluster_records) == 1  # NOT auto-merged
    possibles = [
        m
        for m in unified.resolution.other_candidates
        if m.decision == MatchDecision.POSSIBLE_MATCH
    ]
    assert possibles, "the cross-silo possible match must be surfaced"
    assert any("possible" in note for note in unified.resolution.notes)


async def test_not_found(orchestrator):
    with pytest.raises(EntityNotFoundError):
        await orchestrator.get_unified(
            "Counterparty", {"national_tax_code": "IT00000000099"}
        )


async def test_unknown_entity(orchestrator):
    with pytest.raises(KeyError):
        await orchestrator.get_unified("Instrument", {"legal_name": "x"})


async def test_explain_cache_roundtrip(orchestrator):
    unified = await orchestrator.get_unified("Counterparty", ACME_TAX)
    assert orchestrator.explain(unified.request_id) is unified
    assert orchestrator.explain("nope") is None


# ── governance ───────────────────────────────────────────────────────────


class DenyCrmPolicy(GovernancePolicy):
    def check(self, request: FetchRequest) -> PolicyDecision:
        if request.source == "crm":
            return PolicyDecision(allowed=False, reason="residency: CRM offshore")
        return PolicyDecision(allowed=True, reason="ok")


class CountingPolicy(GovernancePolicy):
    def __init__(self):
        self.requests: list[FetchRequest] = []

    def check(self, request: FetchRequest) -> PolicyDecision:
        self.requests.append(request)
        return PolicyDecision(allowed=True, reason="ok")


async def test_policy_denial_excludes_source():
    orchestrator = build_orchestrator(
        policy=DenyCrmPolicy(), simulated_latency_s=0.0
    )
    unified = await orchestrator.get_unified("Counterparty", ACME_TAX)
    assert {r.source for r in unified.resolution.cluster_records} == {"core_banking"}
    assert unified.resolution.sources_denied == ["crm: residency: CRM offshore"]


async def test_policy_checked_on_every_fetch_including_relationships():
    policy = CountingPolicy()
    orchestrator = build_orchestrator(policy=policy, simulated_latency_s=0.0)
    await orchestrator.get_unified("Counterparty", ACME_TAX)
    # 2 source searches + 1 relationship expansion (ACME -> controller)
    assert len(policy.requests) == 3
    purposes = [r.purpose for r in policy.requests]
    assert purposes.count("resolution") == 2
    assert purposes.count("relationship_expansion") == 1


# ── concurrency ──────────────────────────────────────────────────────────


async def test_sources_are_fetched_concurrently():
    latency = 0.15
    orchestrator = build_orchestrator(simulated_latency_s=latency)
    t0 = time.perf_counter()
    await orchestrator.resolve("Counterparty", ACME_TAX)
    elapsed = time.perf_counter() - t0
    assert elapsed < 2 * latency, (
        f"fetch took {elapsed:.3f}s — sources appear to be fetched serially"
    )


# ── neutrality: adapter swap without orchestrator changes ────────────────


class AltCrmAdapter(SourceAdapter):
    """A differently-implemented CRM adapter. The orchestrator must produce
    identical correlations through the same interface."""

    def __init__(self, source_id, ontology):
        super().__init__(source_id, ontology)
        self._delegate = MockCrmAdapter(source_id, ontology, simulated_latency_s=0.0)

    async def search(self, entity_type, criteria):
        return await self._delegate.search(entity_type, criteria)

    async def get(self, entity_type, key):
        return await self._delegate.get(entity_type, key)


async def test_adapter_swap_is_transparent(orchestrator, ontology):
    baseline = await orchestrator.get_unified("Counterparty", ACME_TAX)

    swapped = FederationOrchestrator(
        graph=orchestrator.graph,
        adapters={
            "core_banking": orchestrator._adapters["core_banking"],
            "crm": AltCrmAdapter("crm", ontology),
        },
        policy=AllowAllPolicy(),
        engine=orchestrator._engine,
    )
    unified = await swapped.get_unified("Counterparty", ACME_TAX)
    assert [r.source_key for r in unified.resolution.cluster_records] == [
        r.source_key for r in baseline.resolution.cluster_records
    ]
    assert unified.canonical["legal_name"].value == (
        baseline.canonical["legal_name"].value
    )
