"""Ontology loading, validation errors that name the YAML path, graph queries."""
import copy

import pytest
import yaml

from hubgentic.ontology.loader import OntologyValidationError, load_ontology


def _write_mutated(tmp_path, ontology_path, mutate):
    doc = yaml.safe_load(ontology_path.read_text())
    mutate(doc)
    out = tmp_path / "ontology.yaml"
    out.write_text(yaml.safe_dump(doc))
    return out


def test_loads_valid_ontology(ontology):
    assert ontology.meta.name == "financial-services-core"
    assert set(ontology.sources) == {"core_banking", "crm"}
    assert "Counterparty" in ontology.entities
    # binding order is the canonical-merge preference order
    assert ontology.sources_for("Counterparty") == ["core_banking", "crm"]


def test_shorthand_field_binding_expands(ontology):
    binding = ontology.binding("Counterparty", "core_banking")
    assert binding.fields["legal_name"].source_field == "NAME_TXT"
    assert binding.fields["legal_name"].transform is None


def test_map_transform_roundtrip(ontology):
    fb = ontology.binding("Counterparty", "core_banking").fields["party_type"]
    assert fb.to_ontology_value("P") == "individual"
    assert fb.to_ontology_value("O") == "legal_entity"
    assert fb.to_native_value("individual") == "P"
    assert fb.to_ontology_value(None) is None


def test_relationship_binding_direction(ontology):
    rb = ontology.binding("Counterparty", "core_banking").relationships["controls"]
    assert rb.source_field == "CONTROLLING_CIF_ID"
    assert rb.direction == "inbound"


def test_unknown_source_in_binding_fails(tmp_path, ontology_path):
    def mutate(doc):
        doc["bindings"]["Counterparty"]["mainframe"] = copy.deepcopy(
            doc["bindings"]["Counterparty"]["core_banking"]
        )

    path = _write_mutated(tmp_path, ontology_path, mutate)
    with pytest.raises(OntologyValidationError, match="bindings.Counterparty.mainframe"):
        load_ontology(path)


def test_unknown_attribute_in_binding_fails(tmp_path, ontology_path):
    def mutate(doc):
        doc["bindings"]["Counterparty"]["crm"]["fields"]["swift_bic"] = "BIC__c"

    path = _write_mutated(tmp_path, ontology_path, mutate)
    with pytest.raises(OntologyValidationError, match="swift_bic"):
        load_ontology(path)


def test_unknown_normalizer_fails(tmp_path, ontology_path):
    def mutate(doc):
        doc["entities"]["Counterparty"]["attributes"]["email"]["normalizer"] = "nope"

    path = _write_mutated(tmp_path, ontology_path, mutate)
    with pytest.raises(OntologyValidationError, match="unknown normalizer 'nope'"):
        load_ontology(path)


def test_invalid_applies_to_fails(tmp_path, ontology_path):
    def mutate(doc):
        doc["entities"]["Counterparty"]["attributes"]["date_of_birth"][
            "applies_to"
        ] = ["robot"]

    path = _write_mutated(tmp_path, ontology_path, mutate)
    with pytest.raises(OntologyValidationError, match="robot"):
        load_ontology(path)


def test_relationship_target_must_be_declared(tmp_path, ontology_path):
    def mutate(doc):
        doc["entities"]["Counterparty"]["relationships"]["controls"][
            "target"
        ] = "Account"

    path = _write_mutated(tmp_path, ontology_path, mutate)
    with pytest.raises(OntologyValidationError, match="Account"):
        load_ontology(path)


# ── graph interface ──────────────────────────────────────────────────────


def test_graph_entities_and_attributes(graph):
    assert graph.entity_types() == ["Counterparty"]
    attrs = graph.attributes_of("Counterparty")
    assert {
        "party_type",
        "legal_name",
        "national_tax_code",
        "lei",
        "date_of_birth",
        "incorporation_date",
        "email",
    } == set(attrs)
    assert attrs["lei"].identifying is True


def test_graph_sources_in_binding_order(graph):
    assert graph.sources_for("Counterparty") == ["core_banking", "crm"]
    assert set(graph.sources()) == {"core_banking", "crm"}


def test_graph_binding_lookup(graph):
    binding = graph.binding_for("Counterparty", "crm")
    assert binding.object == "Account"
    assert "lei" not in binding.fields  # CRM legitimately has no LEI
    with pytest.raises(KeyError):
        graph.binding_for("Counterparty", "mainframe")
    with pytest.raises(KeyError):
        graph.attributes_of("Nonexistent")


def test_graph_relationships(graph):
    rels = graph.relationships_of("Counterparty")
    assert rels["controls"].target == "Counterparty"
