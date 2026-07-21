# ARCHITECTURE — hubgentic v0

A vendor-neutral, MCP-exposed federated semantic catalog. This document maps
the components, the request lifecycle, the interfaces that make every tier
swappable, and the ontology YAML schema. Scope and phasing live in
[PLAN.md](PLAN.md).

## Component map

```
MCP client (agent)
   │ stdio
┌──▼──────────────────────────────────────────────┐
│ server/mcp_server.py  (only module importing mcp.*)
│  tools: list_ontology · describe_entity ·        │
│  resolve_entity · get_unified_entity ·           │
│  explain_lineage                                 │
└──┬──────────────────────────────────────────────┘
┌──▼──────────────── federation/orchestrator.py ──┐
│ 1 ontology bindings → which sources hold entity  │
│ 2 GovernancePolicy.check() per fetch (AllowAll)  │
│ 3 concurrent adapter fetch (anyio task group)    │
│ 4 project native records → CandidateRecord       │
│ 5 ResolutionEngine.resolve() → clusters + rules  │
│ 6 merge → UnifiedEntity (all values + canonical, │
│   every value provenance-stamped)                │
│ Request-scoped; no persistence.                  │
└──┬───────────────┬───────────────┬──────────────┘
ontology/          sources/         resolution/
model+loader+graph SourceAdapter    Matcher pipeline
(YAML→pydantic→    iface + 2 mocks  (deterministic →
 OntologyGraph                       normalized → fuzzy)
 iface, networkx impl)
```

Composition happens in one place — `app.build_orchestrator()` — which
instantiates adapters purely from the ontology's source registry
(`module:Class` import paths). Nothing else knows which vendor sits behind a
source id.

## Request lifecycle (`get_unified_entity`)

1. `OntologyGraph.sources_for(entity)` — which sources bind this entity, in
   declared order (that order is also the canonical-merge preference).
2. For each source, `GovernancePolicy.check(FetchRequest)` — a denied source
   is excluded and recorded in `resolution.sources_denied`; v0 ships
   `AllowAllPolicy` but the call sites are real.
3. Allowed sources are fetched **concurrently** (anyio task group) via
   `SourceAdapter.search(entity_type, criteria)` — criteria are ontology-level
   and translated to native fields by each adapter.
4. Native records are projected into ontology attribute space
   (`CandidateRecord`), applying field transforms (e.g. `CUST_TYPE: P →
   individual`) and remembering the native field per attribute for provenance.
5. `ResolutionEngine.resolve()` runs the matcher pipeline over candidate pairs
   and clusters MATCH edges (union-find). Every outcome names the exact rule
   and confidence.
6. The cluster (or singleton) best matching the criteria is merged:
   - `fields[attr]` = **every** source's value, each wrapped in `Provenance`
     (source, native object/field, record key, fetch timestamp, resolution
     rule, confidence);
   - `canonical[attr]` = first non-null in binding order — an explicit,
     auditable policy, stated in `resolution.notes`;
   - relationships are expanded from relationship bindings (policy-checked
     `get()` per referenced record);
   - possible-but-unmerged matches surface in `resolution.other_candidates`.
7. The result is cached in memory (TTL 15 min) under `request_id` so
   `explain_lineage` can answer later; nothing is written to disk.

## Resolution semantics

Default pipeline (order matters):

| # | rule id | decisive when | note |
|---|---|---|---|
| 1 | `deterministic.lei` | raw equality → MATCH 1.0 | inequality ABSTAINs (may be dirt) |
| 2 | `deterministic.tax_code` | raw equality → MATCH 1.0 | idem |
| 3 | `normalized.lei` | canonical equality → MATCH 0.98; canonical **inequality → NO_MATCH** | key conflict is decisive — defeats homonyms |
| 4 | `normalized.tax_code` | idem | |
| 5 | `fuzzy.name_dob_email` | weighted name (0.5) + DOB/incorporation (0.3) + email (0.2), weights renormalized over available signals | `party_type` conflict → NO_MATCH; ≥0.92 MATCH, ≥0.75 POSSIBLE_MATCH, else NO_MATCH |

The first non-ABSTAIN decision per pair wins. Thresholds and the matcher
subset/order are per-request (`ResolutionConfig`). An ML matcher is one class
implementing `Matcher.compare()`; a smarter blocking strategy is one class
implementing `CandidateGenerator.generate()` (v0 uses the all-pairs generator,
which also catches near-duplicates inside a single source).

## Interfaces (the swap points)

- `sources/base.py` — `SourceAdapter.search()/get()` + `SourceRecord`. The two
  mocks implement it; a real SAP/Salesforce/MCP adapter replaces a mock with
  zero orchestrator changes (`tests/test_orchestrator.py::test_adapter_swap_is_transparent`,
  plus the conformance suite in `tests/test_adapters.py` which any new adapter
  should pass).
- `resolution/base.py` — `Matcher`, `CandidateGenerator`, `ResolutionEngine`,
  and the result vocabulary (`MatchResult` with rule id + confidence +
  per-attribute evidence).
- `governance/policy.py` — `GovernancePolicy.check(FetchRequest) →
  PolicyDecision`; consulted before **every** fetch, including relationship
  expansion (purpose-tagged).
- `ontology/graph.py` — `OntologyGraph`; the networkx implementation is an
  in-memory detail behind it.

## Ontology YAML schema (v0.1)

Instance: [ontology/counterparty.yaml](ontology/counterparty.yaml). Pydantic
models: `src/hubgentic/ontology/model.py`.

```yaml
ontology: {name: ..., version: ...}
sources:                      # registry of federated systems
  <source_id>:
    kind: mock | sap | jdbc | mcp | rest ...
    adapter: package.module:ClassName    # dynamic import; ctor(source_id=, ontology=)
    description: ...
entities:
  <EntityName>:
    description: ...
    attributes:
      <attr>:                 # shorthand not allowed here; use mapping form
        type: string | date | enum
        values: [...]         # enum only
        required: true|false
        identifying: true|false          # usable as resolution key/signal
        normalizer: <name in resolution/normalize.py registry>
        applies_to: [<party_type values>]   # attribute scoping
    relationships:
      <rel>: {target: <EntityName>, cardinality: ..., description: ...}
bindings:
  <EntityName>:               # per source, in CANONICAL-MERGE PREFERENCE ORDER
    <source_id>:
      object: <native object/table>
      key_fields: [<native pk>]
      fields:
        <attr>: NATIVE_FIELD                     # shorthand
        <attr>: {source_field: F, transform: map, mapping: {native: ontology}}
      relationships:
        <rel>: {source_field: F, references: <native pk>, direction: outbound|inbound}
```

Validation: pydantic structural checks plus cross-reference checks (bindings
name declared sources/entities/attributes, relationship targets exist,
`applies_to` ⊆ the `party_type` enum, normalizers exist in the registry).
Errors name the offending YAML path.

## Neutrality and lineage, by construction

- No adapter, matcher, or merge step ever special-cases a vendor. Source
  preference exists in exactly one visible place: binding order in the YAML.
- `UnifiedEntity.fields` always carries every source's value; `canonical` is
  an annotated selection, not a replacement.
- `Provenance` is required on every value — the models make it impossible to
  emit an unattributed datum.
- Correlation is ephemeral: the only state is the TTL-bounded in-memory
  explanation cache (`federation/cache.py`).

## v0 non-goals

No real credentials, no write-back, no aggregation, no UI, no auth server, no
performance work beyond concurrent fetch. Read-only correlation only.
