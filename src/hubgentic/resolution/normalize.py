"""Canonicalization helpers shared by matchers, adapters, and the ontology.

The ontology references these by name (attribute `normalizer:`); the loader
validates the names against NORMALIZERS at load time.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any


def normalize_tax_code(value: Any) -> str | None:
    s = re.sub(r"[^A-Z0-9]", "", str(value).upper())
    return s or None


def normalize_lei(value: Any) -> str | None:
    s = re.sub(r"[^A-Z0-9]", "", str(value).upper())
    return s or None


def normalize_email(value: Any) -> str | None:
    s = str(value).strip().lower()
    return s or None


def normalize_person_or_org_name(value: Any) -> str | None:
    # "S.p.A." -> "SPA" (dots removed before punctuation becomes whitespace)
    s = str(value).upper().replace(".", "")
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    s = " ".join(s.split())
    return s or None


NORMALIZERS: dict[str, Callable[[Any], Any]] = {
    "tax_code": normalize_tax_code,
    "lei": normalize_lei,
    "email": normalize_email,
    "person_or_org_name": normalize_person_or_org_name,
}


def normalize(name: str, value: Any) -> Any:
    if value is None:
        return None
    return NORMALIZERS[name](value)
