"""Mock core banking adapter — CIF master, strict/structured data.

Search semantics mimic a bank host system: identifying keys compare after
canonicalization (host uppercases on entry), names support token search
(every query token must appear in NAME_TXT), dates compare exactly.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import anyio

from hubgentic.ontology.model import Ontology
from hubgentic.resolution.normalize import NORMALIZERS
from hubgentic.sources.base import SourceAdapter, SourceRecord
from hubgentic.sources.seeds.core_banking import CIF_ROWS


class MockCoreBankingAdapter(SourceAdapter):
    def __init__(
        self,
        source_id: str,
        ontology: Ontology,
        rows: list[dict] | None = None,
        simulated_latency_s: float = 0.02,
    ) -> None:
        super().__init__(source_id, ontology)
        self._rows = rows if rows is not None else CIF_ROWS
        self._latency = simulated_latency_s

    async def search(
        self, entity_type: str, criteria: dict[str, Any]
    ) -> list[SourceRecord]:
        binding = self.binding(entity_type)
        await anyio.sleep(self._latency)
        matches = []
        for row in self._rows:
            if self._row_matches(row, entity_type, criteria):
                matches.append(self._to_record(binding.object, binding, row))
        return matches

    async def get(self, entity_type: str, key: str) -> SourceRecord | None:
        binding = self.binding(entity_type)
        await anyio.sleep(self._latency)
        key_field = binding.key_fields[0]
        for row in self._rows:
            if str(row[key_field]) == key:
                return self._to_record(binding.object, binding, row)
        return None

    def _row_matches(
        self, row: dict, entity_type: str, criteria: dict[str, Any]
    ) -> bool:
        binding = self.binding(entity_type)
        attributes = self._ontology.entities[entity_type].attributes
        for attr, wanted in criteria.items():
            field_binding = binding.fields.get(attr)
            if field_binding is None:
                return False  # cannot evaluate this predicate here
            native_wanted = field_binding.to_native_value(wanted)
            actual = row.get(field_binding.source_field)
            if actual is None or native_wanted is None:
                return False
            if attr == "legal_name":
                if not self._name_tokens_match(str(native_wanted), str(actual)):
                    return False
                continue
            attr_def = attributes.get(attr)
            if attr_def is not None and attr_def.normalizer:
                norm = NORMALIZERS[attr_def.normalizer]
                if norm(native_wanted) != norm(actual):
                    return False
                continue
            if str(native_wanted).strip() != str(actual).strip():
                return False
        return True

    @staticmethod
    def _name_tokens_match(query: str, stored: str) -> bool:
        norm = NORMALIZERS["person_or_org_name"]
        q, s = norm(query), norm(stored)
        if q is None or s is None:
            return False
        return set(q.split()).issubset(set(s.split()))

    def _to_record(self, obj: str, binding, row: dict) -> SourceRecord:
        return SourceRecord(
            source=self.source_id,
            object=obj,
            key=str(row[binding.key_fields[0]]),
            fields=dict(row),
            fetched_at=datetime.now(UTC),
        )
