# PLAN — v0 Federated Semantic Catalog ("hubgentic")

## Context

Regulated financial institutions cannot centralize data (banking secrecy, residency,
supervisory constraints), so AI agents cannot reason across core banking, CRM, and
KYC/AML silos. This service holds a vendor-neutral ontology, binds it to fields in
each system of record, resolves entities across those systems **at query time**, and
exposes the correlated view to agents over MCP. Differentiators: **neutrality** (no
system is privileged as the hub) and **lineage** (every returned datum is
provenance-annotated by construction).

**v0 exists to prove the hardest claim**: entity resolution across live federated
sources, request-scoped, with full provenance. Everything else is scaffolding around
that proof. All sources are mocked; federation is read-only correlation; nothing is
held at rest.

## v0 acceptance criteria

1. `uv run demo` resolves one counterparty across two mock silos and prints the
   unified entity with its full lineage tree.
2. An MCP client (e.g. Claude Code, MCP Inspector) can call `list_ontology`,
   `describe_entity`, `resolve_entity`, `get_unified_entity`, `explain_lineage`
   against the server over stdio.
3. Every field in a unified entity carries: source system, source object + field,
   source record key, fetch timestamp, resolution rule id, resolution confidence.
4. Resolution test suite passes covering: clean shared-key match (tax code
   cross-source; LEI with synthetic records), normalized
   deterministic match (dirty tax code), fuzzy match with no shared key
   (name+DOB/email), near-duplicates within one source, and true negatives
   (similar name, conflicting key → NO_MATCH).
5. Swapping a mock adapter for another `SourceAdapter` implementation requires zero
   changes to the orchestrator (enforced by an interface-conformance test that runs
   against every registered adapter).

## Stack (verified 2026-07-01)

- Python 3.12, managed with `uv`.
- `mcp[cli] >=1.28,<2` — official MCP Python SDK, stable line. **Pinned `<2`**: a
  `2.0.0b1` pre-release with a breaking API (`MCPServer` replaces `FastMCP`) is
  already on PyPI. Verified against installed 1.28.1: `from mcp.server.fastmcp
  import FastMCP`; `@mcp.tool()` supports `async def`; returning a Pydantic
  `BaseModel` emits an `outputSchema` and structured content; `mcp.run()` defaults
  to stdio.
- `pydantic >=2.7` for all models; `pyyaml` for the ontology; `networkx >=3` behind
  the `OntologyGraph` interface; `rapidfuzz` for fuzzy string comparison (pure
  wheel, no heavy deps); `pytest` + `pytest-asyncio` (dev).

## Module layout

```
hubgentic/
├── PLAN.md / ARCHITECTURE.md / README.md
├── pyproject.toml                      # uv-managed; [project.scripts] demo = ...
├── ontology/counterparty.yaml          # the ontology + bindings (proposed, see file)
├── src/hubgentic/
│   ├── ontology/    model.py loader.py graph.py      # YAML → pydantic → graph iface
│   ├── sources/     base.py mock_core_banking.py mock_crm.py seeds/
│   ├── resolution/  base.py engine.py normalize.py matchers/{deterministic,normalized,fuzzy}.py
│   ├── federation/  orchestrator.py
│   ├── governance/  policy.py                        # GovernancePolicy iface + AllowAll
│   ├── lineage/     model.py                         # Provenance, ProvenancedValue, UnifiedEntity
│   ├── server/      mcp_server.py                    # FastMCP tool definitions
│   └── demo.py
└── tests/           test_{ontology,adapters,resolution,orchestrator,mcp_tools}.py
```

## Phases

Each phase lands with its tests; the resolution engine is the largest single phase.

1. **Scaffold** — `uv init`, pyproject, package skeleton, pytest wiring,
   `uv run demo` stub. *Exit: `uv run pytest` green on a placeholder test.*
2. **Ontology** — pydantic models for the YAML schema, loader with validation
   errors that name the offending YAML path, `OntologyGraph` interface +
   networkx implementation. *Exit: `counterparty.yaml` loads; bad YAML fails
   with actionable errors; graph answers "which sources bind entity X / attribute Y".*
3. **Lineage + governance models** — `Provenance`, `ProvenancedValue`,
   `UnifiedEntity`, `GovernancePolicy` interface + `AllowAllPolicy`. Built before
   adapters so every fetch is provenance-stamped and policy-checked from day one.
4. **Source adapters** — `SourceAdapter` interface (async `search`/`get`),
   both mocks, seed data (~15 records each; overlap matrix specified below).
   *Exit: adapter-conformance test passes for both mocks.*
5. **Resolution engine (core)** — matcher interface as proposed in
   `src/hubgentic/resolution/base.py`, the three matchers, pipeline engine with
   short-circuit semantics, normalization helpers. *Exit: the five resolution
   scenarios in acceptance criterion 4 pass; every result names its rule.*
6. **Federation orchestrator** — bindings → source selection → concurrent
   fetch (via `anyio` task group, already an MCP dependency) → policy check →
   resolution → merge with provenance. Request-scoped only.
7. **MCP server** — the five tools over stdio, Pydantic outputs for structured
   content; in-process smoke test using the SDK's client session.
8. **Demo + README** — `uv run demo` end-to-end run with lineage tree rendering.

## Seed-data overlap matrix (drives the resolution tests)

| Case | core_banking | crm | Expected outcome |
|---|---|---|---|
| Clean key | tax code `IT01234567890` | same tax code | MATCH via `deterministic.tax_code`, conf 1.0 |
| Dirty key | tax code `RSSMRA80A01H501U` | ` rssmra80a01h501u ` | MATCH via `normalized.tax_code` |
| No shared key | structured name + DOB | free-text name variant + same email | MATCH via `fuzzy.name_dob_email`, conf ≥ threshold |
| Near-duplicate | one CIF | two CRM accounts, same entity | both CRM records cluster to one entity |
| Trap: sibling | "Maria Rossi", DOB A | "Mario Rossi", DOB B | NO_MATCH (fuzzy below threshold) |
| Trap: homonym | same name, tax code X | same name, tax code Y | NO_MATCH via normalized key conflict short-circuit |
| True negative | unique records | unique records | remain unmatched, still returned with provenance |

The CRM deliberately has **no LEI field** (per spec), so the cross-source
clean-key path runs on the national tax code; the `deterministic.lei` /
`normalized.lei` matchers are exercised with synthetic records in unit tests.

Plus one `controls` relationship in core_banking (beneficial owner) to prove
relationship traversal in the unified view. Data is Italian-flavoured (codice
fiscale as `national_tax_code`), mixing individuals and legal entities.

## Decisions made (veto in review if wrong)

- **One `Counterparty` entity** with `party_type ∈ {individual, legal_entity}` and
  `applies_to`-scoped attributes (`date_of_birth` vs `incorporation_date`), rather
  than two entity types. Simpler graph, matches how CIFs actually model it.
- **Neutral merge**: the unified view always returns **all** source values per
  attribute with provenance; a `canonical` value is additionally selected by an
  explicit, auditable merge policy (v0: first non-null in the binding order declared
  in the YAML — a visible policy choice, not a hidden hub preference).
- **`explain_lineage`** is served from an **in-memory, TTL-bounded (15 min)
  explanation cache** keyed by the `request_id` returned by `get_unified_entity`;
  it can also recompute from the original query. Nothing touches disk — "nothing at
  rest" is interpreted as no persistence, not no working memory.
- **Pairwise matcher interface + separate `CandidateGenerator` (blocking)
  interface.** v0 blocking is the cross-source cross product (~15×15 — trivial);
  ML/embedding matchers later drop in as either a new `Matcher` or a smarter
  `CandidateGenerator` without touching the engine.
- **Deterministic key conflict is decisive**: two records bearing *different* LEIs
  (or tax codes) are NO_MATCH and short-circuit the pipeline — this is what defeats
  the homonym trap. Missing keys → ABSTAIN, fall through to the next matcher.
- Adapter `search()` accepts ontology-level criteria; each adapter translates to its
  native fields via the bindings. Mocks implement exact + prefix matching only.

## Risks

- **SDK v2 migration** — pinned `<2`; `server/mcp_server.py` is the only module that
  imports `mcp.*`, so the eventual port is contained.
- **Fuzzy thresholds are hand-tuned** on seed data; fine for v0 whose point is the
  *interface* (rule id + confidence on every match), not matcher quality.
- **Latency claim** is only smoke-tested here (mock adapters with artificial delay,
  concurrent fetch asserted); real-source latency is a v1 question.

## Deliverables now on disk for review

- This file; [ARCHITECTURE.md](ARCHITECTURE.md) — components, data flow, interfaces,
  YAML schema spec; [ontology/counterparty.yaml](ontology/counterparty.yaml) —
  proposed ontology instance; [src/hubgentic/resolution/base.py](src/hubgentic/resolution/base.py)
  — proposed entity-resolution interface (importable, no engine behind it yet).

**Nothing else is implemented. Awaiting go-ahead.**
