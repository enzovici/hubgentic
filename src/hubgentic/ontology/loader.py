"""YAML -> validated Ontology, with errors that name the offending YAML path."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from hubgentic.ontology.model import Ontology
from hubgentic.resolution.normalize import NORMALIZERS


class OntologyValidationError(ValueError):
    """Raised when an ontology document fails structural or semantic validation."""


def _format_pydantic_error(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "<document root>"
        lines.append(f"  {loc}: {err['msg']}")
    return "\n".join(lines)


def load_ontology(path: str | Path) -> Ontology:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise OntologyValidationError(f"{path}: document root must be a mapping")

    try:
        ontology = Ontology.model_validate(raw)
    except ValidationError as exc:
        raise OntologyValidationError(
            f"{path}: invalid ontology document\n{_format_pydantic_error(exc)}"
        ) from exc

    # Semantic check beyond the schema: normalizer names must exist in the
    # shared registry, otherwise resolution would fail at query time.
    for entity_name, entity in ontology.entities.items():
        for attr_name, attr in entity.attributes.items():
            if attr.normalizer is not None and attr.normalizer not in NORMALIZERS:
                raise OntologyValidationError(
                    f"{path}: entities.{entity_name}.attributes.{attr_name}: "
                    f"unknown normalizer '{attr.normalizer}' "
                    f"(known: {sorted(NORMALIZERS)})"
                )
    return ontology
