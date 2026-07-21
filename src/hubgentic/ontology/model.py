"""Pydantic models for the ontology YAML schema (see ontology/counterparty.yaml).

The document has four top-level sections:
  ontology  — name/version metadata
  sources   — registry of federated systems (adapter import path per source)
  entities  — entity types with typed attributes and relationships
  bindings  — per entity, per source: how ontology attributes map to native
              objects/fields. Binding ORDER is the explicit canonical-merge
              preference order (a visible policy, not a hidden hub preference).
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AttributeType(StrEnum):
    STRING = "string"
    DATE = "date"
    ENUM = "enum"


class AttributeDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: AttributeType
    description: str | None = None
    values: list[str] | None = None  # enum types only
    required: bool = False
    identifying: bool = False  # usable as a resolution key/signal
    normalizer: str | None = None  # name in hubgentic.resolution.normalize registry
    applies_to: list[str] | None = None  # party_type values this attribute applies to

    @model_validator(mode="after")
    def _enum_requires_values(self) -> AttributeDef:
        if self.type == AttributeType.ENUM and not self.values:
            raise ValueError("attribute of type 'enum' requires non-empty 'values'")
        if self.type != AttributeType.ENUM and self.values:
            raise ValueError("'values' is only allowed on attributes of type 'enum'")
        return self


class RelationshipDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str  # target entity type
    cardinality: Literal["one_to_one", "one_to_many", "many_to_many"] = "many_to_many"
    description: str | None = None


class EntityDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    attributes: dict[str, AttributeDef]
    relationships: dict[str, RelationshipDef] = Field(default_factory=dict)


class SourceDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str  # mock | sap | jdbc | mcp | rest ...
    adapter: str  # import path "package.module:ClassName"
    description: str | None = None


class FieldBinding(BaseModel):
    """Maps one ontology attribute to one native field, optionally transformed.

    YAML shorthand `attr: FIELD_NAME` is accepted and expanded to
    `{source_field: FIELD_NAME}`.
    """

    model_config = ConfigDict(extra="forbid")

    source_field: str
    transform: Literal["map"] | None = None
    mapping: dict[str, str] | None = None  # native value -> ontology value

    @model_validator(mode="before")
    @classmethod
    def _expand_shorthand(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"source_field": value}
        return value

    @model_validator(mode="after")
    def _map_requires_mapping(self) -> FieldBinding:
        if self.transform == "map" and not self.mapping:
            raise ValueError("transform 'map' requires a non-empty 'mapping'")
        if self.transform is None and self.mapping:
            raise ValueError("'mapping' is only allowed with transform 'map'")
        return self

    def to_ontology_value(self, native_value: Any) -> Any:
        if native_value is None:
            return None
        if self.transform == "map":
            assert self.mapping is not None
            return self.mapping.get(str(native_value))
        return native_value

    def to_native_value(self, ontology_value: Any) -> Any:
        if ontology_value is None:
            return None
        if self.transform == "map":
            assert self.mapping is not None
            inverse = {v: k for k, v in self.mapping.items()}
            return inverse.get(str(ontology_value))
        return ontology_value


class RelationshipBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_field: str  # native field holding the reference
    references: str  # native key field of the referenced record
    # outbound: this record's field points at the relationship TARGET.
    # inbound: the field points at the record that is the relationship SUBJECT
    # (e.g. CONTROLLING_CIF_ID names the counterparty that controls this one).
    direction: Literal["outbound", "inbound"] = "outbound"


class SourceBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object: str  # native object/table, e.g. "CIF" or "Account"
    key_fields: list[str]
    fields: dict[str, FieldBinding]  # ontology attribute -> native field
    relationships: dict[str, RelationshipBinding] = Field(default_factory=dict)


class OntologyMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str


class Ontology(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    meta: OntologyMeta = Field(alias="ontology")
    sources: dict[str, SourceDef]
    entities: dict[str, EntityDef]
    bindings: dict[str, dict[str, SourceBinding]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _cross_references(self) -> Ontology:
        for entity_name, entity in self.entities.items():
            for rel_name, rel in entity.relationships.items():
                if rel.target not in self.entities:
                    raise ValueError(
                        f"entities.{entity_name}.relationships.{rel_name}: "
                        f"target '{rel.target}' is not a declared entity"
                    )
            party_type = entity.attributes.get("party_type")
            allowed_kinds = set(party_type.values or []) if party_type else set()
            for attr_name, attr in entity.attributes.items():
                if attr.applies_to:
                    unknown = set(attr.applies_to) - allowed_kinds
                    if unknown:
                        raise ValueError(
                            f"entities.{entity_name}.attributes.{attr_name}: "
                            f"applies_to values {sorted(unknown)} are not values of "
                            f"the 'party_type' enum attribute"
                        )
        for entity_name, per_source in self.bindings.items():
            if entity_name not in self.entities:
                raise ValueError(
                    f"bindings.{entity_name}: '{entity_name}' is not a declared entity"
                )
            entity = self.entities[entity_name]
            for source_id, binding in per_source.items():
                where = f"bindings.{entity_name}.{source_id}"
                if source_id not in self.sources:
                    raise ValueError(
                        f"{where}: '{source_id}' is not a declared source"
                    )
                for attr_name in binding.fields:
                    if attr_name not in entity.attributes:
                        raise ValueError(
                            f"{where}.fields.{attr_name}: not an attribute of "
                            f"entity '{entity_name}'"
                        )
                for rel_name in binding.relationships:
                    if rel_name not in entity.relationships:
                        raise ValueError(
                            f"{where}.relationships.{rel_name}: not a relationship "
                            f"of entity '{entity_name}'"
                        )
        return self

    def sources_for(self, entity_type: str) -> list[str]:
        """Sources binding this entity, in declared (merge-preference) order."""
        return list(self.bindings.get(entity_type, {}).keys())

    def binding(self, entity_type: str, source_id: str) -> SourceBinding:
        return self.bindings[entity_type][source_id]
