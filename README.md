# hubgentic

Vendor-neutral, MCP-exposed **federated semantic catalog** for regulated
financial services — v0.

Enterprises in regulated finance can't centralize data into a lakehouse
(banking secrecy, data residency, supervisory constraints). hubgentic lets AI
agents reason across siloed systems of record **without moving the data**: it
holds a definable ontology, binds ontology entities to fields in each source
system, resolves entities across those systems at query time, and exposes the
result over MCP.

Two differentiators, both enforced by construction:

- **Neutrality** — no vendor's system is privileged as the hub. Every source
  sits behind the same `SourceAdapter` interface; the unified view returns
  *all* source values per attribute, and the canonical value is selected by an
  explicit, auditable policy (binding order in the ontology YAML), never a
  hidden preference.
- **Lineage** — every returned field carries full provenance: source system,
  native object/field, record key, fetch timestamp, the exact resolution rule
  that correlated it, and its confidence.

v0 proves the hardest claim — cross-source entity resolution with full
provenance, request-scoped, nothing at rest — against two mocked silos
(a core banking CIF master and a Salesforce-shaped CRM).

## Quickstart

```sh
uv sync          # Python 3.12, managed by uv
uv run pytest    # ontology, adapters, resolution scenarios, orchestrator, MCP
uv run demo      # resolve counterparties across both silos, print lineage trees
```

> **If this checkout lives in iCloud Drive** (as the original does): keep the
> virtualenv in `.venv.nosync` with a `.venv` symlink pointing at it
> (`mv .venv .venv.nosync && ln -s .venv.nosync .venv` after the first sync).
> iCloud marks files under a plain `.venv` with the macOS `hidden` flag, and
> Python ≥3.12 silently skips hidden `.pth` files — which breaks the editable
> install with `ModuleNotFoundError: hubgentic`. iCloud never syncs `*.nosync`
> paths, so the symlinked layout is immune.

## MCP server

```sh
uv run hubgentic-server        # stdio transport
# or explore interactively:
uv run mcp dev src/hubgentic/server/mcp_server.py
# or add to Claude Code:
claude mcp add hubgentic -- uv --directory /path/to/hubgentic run hubgentic-server
```

| Tool | Purpose |
|---|---|
| `list_ontology` | Entity types, attributes, relationships, bound sources |
| `describe_entity` | Typed attributes + per-source field bindings |
| `resolve_entity` | Ranked candidate matches with the exact rule + confidence per pair |
| `get_unified_entity` | One unified, provenance-annotated view (all values + canonical) |
| `explain_lineage` | Full lineage tree for a prior request (or recompute) |

Example call: `get_unified_entity` with
`{"entity_type": "Counterparty", "criteria": {"legal_name": "Lucia Bianchi"}}` —
the CRM record has no tax code, so correlation happens probabilistically
(`fuzzy.name_dob_email`) and the output says exactly that, per field.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the component map, request
lifecycle, the ontology YAML schema, and the extension points (add a source,
add a matcher, replace the graph store). [PLAN.md](PLAN.md) documents v0
scope, the seed-data overlap matrix, and accepted risks.

## v0 non-goals

No real source credentials, no write-back, no aggregation, no UI, no auth
server, no performance work. Read-only correlation; nothing persisted.
