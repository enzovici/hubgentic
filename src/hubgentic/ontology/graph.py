"""Graph view of the ontology behind a swappable interface.

The orchestrator and MCP server depend only on OntologyGraph, so the networkx
implementation can be replaced (e.g. by a real graph store) without touching
them.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import networkx as nx

from hubgentic.ontology.model import (
    AttributeDef,
    Ontology,
    RelationshipDef,
    SourceBinding,
    SourceDef,
)


class OntologyGraph(ABC):
    @abstractmethod
    def entity_types(self) -> list[str]: ...

    @abstractmethod
    def attributes_of(self, entity_type: str) -> dict[str, AttributeDef]: ...

    @abstractmethod
    def relationships_of(self, entity_type: str) -> dict[str, RelationshipDef]: ...

    @abstractmethod
    def sources(self) -> dict[str, SourceDef]: ...

    @abstractmethod
    def sources_for(self, entity_type: str) -> list[str]:
        """Sources binding this entity, in declared (merge-preference) order."""

    @abstractmethod
    def binding_for(self, entity_type: str, source_id: str) -> SourceBinding: ...


class NetworkXOntologyGraph(OntologyGraph):
    """In-memory graph: nodes for entities/attributes/sources, typed edges."""

    def __init__(self, ontology: Ontology) -> None:
        self._ontology = ontology
        g = nx.MultiDiGraph()
        for source_id, source in ontology.sources.items():
            g.add_node(("source", source_id), definition=source)
        for entity_name, entity in ontology.entities.items():
            g.add_node(("entity", entity_name), definition=entity)
            for attr_name, attr in entity.attributes.items():
                attr_node = ("attribute", f"{entity_name}.{attr_name}")
                g.add_node(attr_node, definition=attr, name=attr_name)
                g.add_edge(("entity", entity_name), attr_node, key="has_attribute")
            for rel_name, rel in entity.relationships.items():
                g.add_edge(
                    ("entity", entity_name),
                    ("entity", rel.target),
                    key=f"rel:{rel_name}",
                    definition=rel,
                    name=rel_name,
                )
        for entity_name, per_source in ontology.bindings.items():
            for order, (source_id, binding) in enumerate(per_source.items()):
                g.add_edge(
                    ("entity", entity_name),
                    ("source", source_id),
                    key="bound_in",
                    binding=binding,
                    order=order,
                )
                for attr_name, field_binding in binding.fields.items():
                    g.add_edge(
                        ("attribute", f"{entity_name}.{attr_name}"),
                        ("source", source_id),
                        key="bound_to",
                        field_binding=field_binding,
                    )
        self._graph = g

    def entity_types(self) -> list[str]:
        return [name for kind, name in self._graph.nodes if kind == "entity"]

    def attributes_of(self, entity_type: str) -> dict[str, AttributeDef]:
        self._require_entity(entity_type)
        out: dict[str, AttributeDef] = {}
        for _, node, key in self._graph.out_edges(("entity", entity_type), keys=True):
            if key == "has_attribute":
                data = self._graph.nodes[node]
                out[data["name"]] = data["definition"]
        return out

    def relationships_of(self, entity_type: str) -> dict[str, RelationshipDef]:
        self._require_entity(entity_type)
        out: dict[str, RelationshipDef] = {}
        for _, _, key, data in self._graph.out_edges(
            ("entity", entity_type), keys=True, data=True
        ):
            if key.startswith("rel:"):
                out[data["name"]] = data["definition"]
        return out

    def sources(self) -> dict[str, SourceDef]:
        return {
            name: self._graph.nodes[(kind, name)]["definition"]
            for kind, name in self._graph.nodes
            if kind == "source"
        }

    def sources_for(self, entity_type: str) -> list[str]:
        self._require_entity(entity_type)
        bound: list[tuple[int, str]] = []
        for _, (kind, source_id), key, data in self._graph.out_edges(
            ("entity", entity_type), keys=True, data=True
        ):
            if key == "bound_in" and kind == "source":
                bound.append((data["order"], source_id))
        return [source_id for _, source_id in sorted(bound)]

    def binding_for(self, entity_type: str, source_id: str) -> SourceBinding:
        self._require_entity(entity_type)
        for _, (kind, sid), key, data in self._graph.out_edges(
            ("entity", entity_type), keys=True, data=True
        ):
            if key == "bound_in" and kind == "source" and sid == source_id:
                return data["binding"]
        raise KeyError(
            f"entity '{entity_type}' has no binding for source '{source_id}'"
        )

    def _require_entity(self, entity_type: str) -> None:
        if ("entity", entity_type) not in self._graph.nodes:
            raise KeyError(f"unknown entity type '{entity_type}'")
