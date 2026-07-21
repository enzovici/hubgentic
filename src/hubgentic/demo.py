"""End-to-end demo: resolve counterparties across both mock silos and print
the unified entities with their lineage trees.  Run with `uv run demo`.
"""
from __future__ import annotations

import time
from typing import Any

import anyio

from hubgentic.app import build_orchestrator
from hubgentic.lineage.render import render_lineage_tree


def _hr(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


async def _show(orchestrator, entity_type: str, criteria: dict[str, Any]) -> None:
    t0 = time.perf_counter()
    unified = await orchestrator.get_unified(entity_type, criteria)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    res = unified.resolution
    print(f"criteria          : {criteria}")
    print(f"sources consulted : {', '.join(res.sources_consulted)} (concurrent)")
    print(
        f"records correlated: {len(res.cluster_records)} "
        f"({', '.join(f'{r.source}[{r.source_key}]' for r in res.cluster_records)})"
    )
    for match in res.supporting_matches:
        print(
            f"matched by        : {match.rule}  confidence={match.confidence:.2f}"
        )
    for match in res.other_candidates:
        if match.decision == "possible_match":
            print(
                f"possible match    : {match.rule}  confidence="
                f"{match.confidence:.2f}  (below auto-merge threshold, excluded)"
            )
    print(f"fetch+resolve     : {elapsed_ms:.0f} ms")
    print()
    print(render_lineage_tree(unified))


async def _run() -> None:
    orchestrator = build_orchestrator()

    _hr(
        "1) Legal entity, clean shared key — ACME by tax code\n"
        "   core_banking.CIF and crm.Account correlate via deterministic.tax_code;\n"
        "   beneficial owner surfaced through the 'controls' relationship."
    )
    await _show(
        orchestrator, "Counterparty", {"national_tax_code": "IT01234567890"}
    )

    _hr(
        "2) Individual, NO shared key — Lucia Bianchi by name\n"
        "   The CRM record has no tax code; correlation is probabilistic\n"
        "   (name variant + date of birth + email) via fuzzy.name_dob_email."
    )
    await _show(orchestrator, "Counterparty", {"legal_name": "Lucia Bianchi"})

    print()
    print(
        "Every value above carries: source system, native object/field, record "
        "key,\nfetch timestamp, the exact resolution rule that correlated it, "
        "and its\nconfidence. The same data is exposed over MCP: "
        "`uv run hubgentic-server`."
    )


def main() -> None:
    anyio.run(_run)


if __name__ == "__main__":
    main()
