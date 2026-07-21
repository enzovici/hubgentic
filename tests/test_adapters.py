"""Adapter conformance: every adapter must behave identically through the
SourceAdapter interface — this is the neutrality guarantee at the source tier."""
import importlib
from datetime import UTC

import pytest

from hubgentic.sources.base import SourceAdapter
from hubgentic.sources.mock_core_banking import MockCoreBankingAdapter
from hubgentic.sources.mock_crm import MockCrmAdapter


def _adapters(ontology) -> dict[str, SourceAdapter]:
    return {
        "core_banking": MockCoreBankingAdapter(
            "core_banking", ontology, simulated_latency_s=0.0
        ),
        "crm": MockCrmAdapter("crm", ontology, simulated_latency_s=0.0),
    }


@pytest.fixture(params=["core_banking", "crm"])
def adapter(request, ontology):
    return _adapters(ontology)[request.param]


async def test_search_by_tax_code_finds_acme(adapter):
    records = await adapter.search(
        "Counterparty", {"national_tax_code": "IT01234567890"}
    )
    assert len(records) == 1
    record = records[0]
    assert record.source == adapter.source_id
    assert record.object in {"CIF", "Account"}
    assert record.key
    assert record.fetched_at.tzinfo is not None


async def test_search_by_name_tokens(adapter):
    records = await adapter.search("Counterparty", {"legal_name": "Lucia Bianchi"})
    assert len(records) == 1


async def test_get_roundtrip(adapter):
    [record] = await adapter.search(
        "Counterparty", {"national_tax_code": "IT01234567890"}
    )
    again = await adapter.get("Counterparty", record.key)
    assert again is not None
    assert again.key == record.key
    assert again.fields == record.fields


async def test_get_missing_returns_none(adapter):
    assert await adapter.get("Counterparty", "NO-SUCH-KEY") is None


async def test_unknown_entity_raises(adapter):
    with pytest.raises(KeyError):
        await adapter.search("Instrument", {"legal_name": "x"})


async def test_multi_criteria_conjunction(adapter):
    # name matches several Rossi records; DOB narrows to exactly one person
    records = await adapter.search(
        "Counterparty", {"legal_name": "Rossi", "date_of_birth": "1980-01-01"}
    )
    assert len(records) == 1


async def test_unbound_criterion_yields_empty_not_fanout(ontology):
    # The CRM does not bind LEI: it must return [], never an unfiltered dump.
    crm = _adapters(ontology)["crm"]
    assert await crm.search("Counterparty", {"lei": "529900ACME000000IT01"}) == []
    cb = _adapters(ontology)["core_banking"]
    assert len(await cb.search("Counterparty", {"lei": "529900ACME000000IT01"})) == 1


async def test_crm_matches_dirty_tax_code(ontology):
    crm = _adapters(ontology)["crm"]
    records = await crm.search(
        "Counterparty", {"national_tax_code": "RSSMRA80A01H501U"}
    )
    assert [r.key for r in records] == ["001A000002"]  # stored as " rssmra… "


def test_declared_adapters_conform_to_interface(ontology):
    """Every adapter in the ontology's source registry is dynamically importable
    and implements SourceAdapter — real adapters must pass this same test."""
    for source_id, source_def in ontology.sources.items():
        module_name, _, class_name = source_def.adapter.partition(":")
        cls = getattr(importlib.import_module(module_name), class_name)
        instance = cls(source_id=source_id, ontology=ontology)
        assert isinstance(instance, SourceAdapter)
