"""Application wiring: ontology file discovery and orchestrator construction.

Adapters are instantiated purely from the ontology's source registry
(module:Class import paths) — the orchestrator never hardcodes a system.
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path

from hubgentic.federation.orchestrator import FederationOrchestrator
from hubgentic.governance.policy import AllowAllPolicy, GovernancePolicy
from hubgentic.ontology.graph import NetworkXOntologyGraph
from hubgentic.ontology.loader import load_ontology
from hubgentic.resolution.engine import PipelineResolutionEngine
from hubgentic.resolution.matchers import default_matchers
from hubgentic.sources.base import SourceAdapter


def find_ontology_path() -> Path:
    env = os.environ.get("HUBGENTIC_ONTOLOGY")
    if env:
        return Path(env)
    candidate = Path.cwd() / "ontology" / "counterparty.yaml"
    if candidate.exists():
        return candidate
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "ontology" / "counterparty.yaml"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "cannot locate ontology/counterparty.yaml — set HUBGENTIC_ONTOLOGY"
    )


def build_orchestrator(
    ontology_path: str | Path | None = None,
    policy: GovernancePolicy | None = None,
    **adapter_kwargs,
) -> FederationOrchestrator:
    ontology = load_ontology(ontology_path or find_ontology_path())
    graph = NetworkXOntologyGraph(ontology)

    adapters: dict[str, SourceAdapter] = {}
    for source_id, source_def in ontology.sources.items():
        module_name, _, class_name = source_def.adapter.partition(":")
        adapter_cls = getattr(importlib.import_module(module_name), class_name)
        adapters[source_id] = adapter_cls(
            source_id=source_id, ontology=ontology, **adapter_kwargs
        )

    return FederationOrchestrator(
        graph=graph,
        adapters=adapters,
        policy=policy or AllowAllPolicy(),
        engine=PipelineResolutionEngine(default_matchers()),
    )
