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

## Web app (multi-tenant early-access UI)

```sh
HUBGENTIC_ADMIN_EMAILS=you@example.com uv run hubgentic-web   # http://127.0.0.1:8000
```

Marketing page, sign-up/login, and per-workspace app: Explorer (unified entity
+ provenance + resolution evidence), Ontology mapping matrix, per-workspace
source governance, audit log, API keys, members/invites with roles
(owner/admin/member), and a feedback widget whose notes land in the founder
console at `/admin` (visible to `HUBGENTIC_ADMIN_EMAILS`).

Tenancy: workspace URLs carry the slug (`/app/<slug>/…`) and membership is
re-checked on every request; each workspace gets its own orchestrator (so the
lineage cache is never shared) and its own governance policy. Auth is stdlib
only: scrypt password hashes, server-side sessions (SHA-256 of the token
stored), per-session CSRF tokens, cross-origin POST rejection, login
throttling. API keys are workspace-scoped and hashed at rest.

REST: `POST /api/v1/unified`, `GET /api/v1/ontology`,
`GET /api/v1/lineage/{request_id}` with `Authorization: Bearer hg_live_…`.

| Env var | Default | |
|---|---|---|
| `HUBGENTIC_DB` | `./var/hubgentic.db` | SQLite file (accounts only; catalog data never stored) |
| `HUBGENTIC_ADMIN_EMAILS` | — | comma-separated founder-console access |
| `HUBGENTIC_SIGNUP` | `open` | set `invite` to require an invite link |
| `HUBGENTIC_SECURE_COOKIES` | `0` | set `1` behind HTTPS (the Dockerfile does) |

Deploy anywhere that runs a container with a persistent volume at `/data`
(Fly.io, Railway, Render): `docker build -t hubgentic . && docker run -p 8000:8000 -v hg:/data hubgentic`.
Single-process SQLite is fine for early access; move to Postgres before
running more than one instance.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the component map, request
lifecycle, the ontology YAML schema, and the extension points (add a source,
add a matcher, replace the graph store). [PLAN.md](PLAN.md) documents v0
scope, the seed-data overlap matrix, and accepted risks.

## v0 non-goals

No real source credentials, no write-back, no aggregation, no SSO/email
verification, no performance work. Read-only correlation; nothing persisted.
