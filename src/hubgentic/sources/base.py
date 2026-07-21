"""Source adapter interface.

Adapters speak ONTOLOGY-level criteria (attribute name -> value) and translate
them to native fields via the bindings they were constructed with; they return
records in NATIVE field space. Projection back to ontology space is the
orchestrator's job. Real SAP/Salesforce/MCP adapters implement exactly this
interface — the orchestrator never learns which is which.

Adapter contract for dynamic loading (SourceDef.adapter = "module:Class"):
the class must be constructible as Class(source_id=..., ontology=...).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from hubgentic.ontology.model import Ontology, SourceBinding


class SourceRecord(BaseModel):
    """One native record as fetched from a source system."""

    source: str
    object: str           # native object/table name
    key: str              # native primary key value
    fields: dict[str, Any]  # NATIVE field name -> value
    fetched_at: datetime


class SourceAdapter(ABC):
    def __init__(self, source_id: str, ontology: Ontology) -> None:
        self.source_id = source_id
        self._ontology = ontology

    def binding(self, entity_type: str) -> SourceBinding:
        try:
            return self._ontology.binding(entity_type, self.source_id)
        except KeyError:
            raise KeyError(
                f"source '{self.source_id}' has no binding for entity "
                f"'{entity_type}'"
            ) from None

    @abstractmethod
    async def search(
        self, entity_type: str, criteria: dict[str, Any]
    ) -> list[SourceRecord]:
        """Records matching ALL criteria (ontology attribute -> value).

        A criterion on an attribute this source does not bind cannot be
        evaluated here and must yield [] (never an unfiltered fan-out).
        """

    @abstractmethod
    async def get(self, entity_type: str, key: str) -> SourceRecord | None:
        """Fetch one record by native primary key."""
