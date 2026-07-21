import pytest

from hubgentic.app import build_orchestrator, find_ontology_path
from hubgentic.ontology.graph import NetworkXOntologyGraph
from hubgentic.ontology.loader import load_ontology


@pytest.fixture(scope="session")
def ontology_path():
    return find_ontology_path()


@pytest.fixture(scope="session")
def ontology(ontology_path):
    return load_ontology(ontology_path)


@pytest.fixture(scope="session")
def graph(ontology):
    return NetworkXOntologyGraph(ontology)


@pytest.fixture
def orchestrator():
    return build_orchestrator(simulated_latency_s=0.0)
