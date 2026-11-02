"""Multi-tenant web app: marketing page, auth, workspace UI and a REST API.

Tenancy model: a user can belong to many workspaces (tenants). Every
workspace URL carries its slug (`/app/<slug>/...`) and every request re-checks
membership, so access never depends on "current tenant" session state. API
keys belong to a workspace, not a user.

Run with `uv run hubgentic-web` (http://127.0.0.1:8000).
"""
from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.exception_handlers import http_exception_handler
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from hubgentic.federation.orchestrator import EntityNotFoundError
from hubgentic.lineage.render import render_lineage_tree
from hubgentic.web import security as sec
from hubgentic.web.graphs import entity_graph, ontology_graph
from hubgentic.web.db import Database, default_db_path, now
from hubgentic.web.tenancy import TenantRuntimes

HERE = Path(__file__).parent
SESSION_COOKIE = "hg_session"
FLASH_COOKIE = "hg_flash"
SESSION_TTL = timedelta(days=14)
INVITE_TTL = timedelta(days=7)
ROLES = ("owner", "admin", "member")

EXAMPLES = [
    {
        "label": "ACME by tax code",
        "hint": "clean shared key",
        "criteria": {"national_tax_code": "IT01234567890"},
    },
    {
        "label": "Lucia Bianchi",
        "hint": "no shared key, fuzzy match",
        "criteria": {"legal_name": "Lucia Bianchi"},
    },
    {
        "label": "Ferrari Logistics",
        "hint": "name variants across systems",
        "criteria": {"legal_name": "Ferrari Logistics"},
    },
    {
        "label": "Mario Rossi",
        "hint": "same name, different people",
        "criteria": {"legal_name": "Mario Rossi"},
    },
]


class HTTPRedirect(Exception):
    def __init__(self, url: str) -> None:
        self.url = url


def create_app(
    db_path: str | Path | None = None,
    *,
    secure_cookies: bool | None = None,
    admin_emails: set[str] | None = None,
    signup_open: bool | None = None,
    **adapter_kwargs: Any,
) -> FastAPI:
    db = Database(db_path or default_db_path())
    runtimes = TenantRuntimes(db, **adapter_kwargs)
    if secure_cookies is None:
        secure_cookies = os.environ.get("HUBGENTIC_SECURE_COOKIES", "0") == "1"
    if admin_emails is None:
        admin_emails = {
            e.strip().lower()
            for e in os.environ.get("HUBGENTIC_ADMIN_EMAILS", "").split(",")
            if e.strip()
        }
    if signup_open is None:
        signup_open = os.environ.get("HUBGENTIC_SIGNUP", "open") == "open"
    login_throttle = sec.Throttle(limit=8, window=300)
    feedback_throttle = sec.Throttle(limit=10, window=3600)

    app = FastAPI(title="hubgentic", docs_url="/api/docs", redoc_url=None)
    app.state.db = db
    app.state.runtimes = runtimes
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.filters["fromjson"] = json.loads
    templates.env.filters["ago"] = _ago

    # ── middleware ───────────────────────────────────────────────────────

    class SecurityHeaders(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Cross-site form posts are rejected outright (login CSRF etc.);
            # authenticated forms additionally carry a per-session token.
            if request.method == "POST" and not request.url.path.startswith("/api/"):
                origin = request.headers.get("origin")
                if origin and urlparse(origin).netloc != request.url.netloc:
                    return Response("cross-origin request rejected", status_code=403)
            response = await call_next(request)
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("Referrer-Policy", "same-origin")
            if secure_cookies:
                # Only meaningful (and only safe) when served over HTTPS.
                response.headers.setdefault(
                    "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
                )
            if not request.url.path.startswith("/api/docs"):
                response.headers.setdefault(
                    "Content-Security-Policy",
                    "default-src 'self'; img-src 'self' data:; "
                    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                    "font-src https://fonts.gstatic.com; script-src 'self'; "
                    "form-action 'self'; frame-ancestors 'none'",
                )
            return response

    app.add_middleware(SecurityHeaders)

    @app.exception_handler(HTTPRedirect)
    async def _redirect(request: Request, exc: HTTPRedirect):
        return RedirectResponse(exc.url, status_code=303)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/api/"):
            return await http_exception_handler(request, exc)
        headings = {403: "Not allowed", 404: "Not found", 429: "Slow down"}
        return render(
            request, "error.html", user=current_session(request), status=exc.status_code,
            heading=headings.get(exc.status_code, "Something went wrong"),
            detail=exc.detail if exc.status_code != 404 else "That page doesn't exist, or you don't have access to it.",
        )

    # ── session helpers ─────────────────────────────────────────────────

    def current_session(request: Request):
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            return None
        row = db.one(
            "SELECT s.csrf, s.expires_at, s.token_hash, u.id, u.email, u.name "
            "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
            sec.token_hash(token),
        )
        if row is None or row["expires_at"] < now():
            return None
        return row

    def require_user(request: Request):
        user = current_session(request)
        if user is None:
            raise HTTPRedirect(f"/login?next={quote(request.url.path)}")
        return user

    def start_session(response: Response, user_id: int) -> None:
        token = sec.new_token()
        db.run(
            "INSERT INTO sessions (token_hash, user_id, csrf, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            sec.token_hash(token), user_id, sec.new_token(16), now(),
            (datetime.now(UTC) + SESSION_TTL).isoformat(timespec="seconds"),
        )
        response.set_cookie(
            SESSION_COOKIE, token, max_age=int(SESSION_TTL.total_seconds()),
            httponly=True, samesite="lax", secure=secure_cookies,
        )

    def flash(response: Response, message: str, kind: str = "ok") -> Response:
        response.set_cookie(
            FLASH_COOKIE, quote(json.dumps({"m": message, "k": kind})),
            max_age=30, httponly=True, samesite="lax", secure=secure_cookies,
        )
        return response

    def redirect(url: str, message: str | None = None, kind: str = "ok") -> Response:
        resp = RedirectResponse(url, status_code=303)
        if message:
            flash(resp, message, kind)
        return resp

    async def form_of(request: Request, user=None) -> dict[str, str]:
        form = await request.form()
        data = {k: v.strip() if isinstance(v, str) else v for k, v in form.items()}
        if user is not None and data.get("csrf") != user["csrf"]:
            raise HTTPException(403, "invalid or missing CSRF token — reload the page")
        return data

    def tenant_for(user, slug: str):
        tenant = db.membership(user["id"], slug)
        if tenant is None:
            # 404, not 403: don't confirm that another tenant's slug exists.
            raise HTTPException(404, "workspace not found")
        return tenant

    def require_role(tenant, *roles: str) -> None:
        if tenant["role"] not in roles:
            raise HTTPException(403, "your role in this workspace cannot do that")

    def render(request: Request, name: str, user=None, tenant=None, status: int = 200, **ctx):
        message = None
        raw = request.cookies.get(FLASH_COOKIE)
        if raw:
            try:
                message = json.loads(unquote(raw))
            except ValueError:
                message = None
        base: dict[str, Any] = {
            "user": user,
            "tenant": tenant,
            "flash": message,
            "csrf": user["csrf"] if user else "",
            "is_staff": bool(user and user["email"].lower() in admin_emails),
            "signup_open": signup_open,
            "path": request.url.path,
            "base": f"/app/{tenant['slug']}" if tenant else "",
        }
        if user is not None:
            base["tenants"] = db.tenants_for_user(user["id"])
        resp = templates.TemplateResponse(request, name, {**base, **ctx}, status_code=status)
        if raw:
            resp.delete_cookie(FLASH_COOKIE)
        return resp

    def unique_slug(name: str) -> str:
        base = sec.slugify(name)
        slug, i = base, 2
        while db.one("SELECT 1 FROM tenants WHERE slug = ?", slug):
            slug, i = f"{base}-{i}", i + 1
        return slug

    def create_tenant(name: str, owner_id: int) -> str:
        slug = unique_slug(name)
        with db.tx() as conn:
            tid = conn.execute(
                "INSERT INTO tenants (slug, name, created_at) VALUES (?, ?, ?)",
                (slug, name, now()),
            ).lastrowid
            conn.execute(
                "INSERT INTO memberships (user_id, tenant_id, role, created_at) "
                "VALUES (?, ?, 'owner', ?)",
                (owner_id, tid, now()),
            )
        return slug

    def accept_invite(token: str, user_id: int) -> str | None:
        inv = db.one(
            "SELECT i.*, t.slug FROM invites i JOIN tenants t ON t.id = i.tenant_id "
            "WHERE i.token_hash = ? AND i.accepted_by IS NULL AND i.expires_at > ?",
            sec.token_hash(token), now(),
        )
        if inv is None:
            return None
        with db.tx() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO memberships (user_id, tenant_id, role, created_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, inv["tenant_id"], inv["role"], now()),
            )
            conn.execute(
                "UPDATE invites SET accepted_by = ? WHERE token_hash = ?",
                (user_id, inv["token_hash"]),
            )
        return inv["slug"]

    def safe_next(url: str | None) -> str:
        if url and url.startswith("/") and not url.startswith("//"):
            return url
        return "/app"

    # ── public pages ────────────────────────────────────────────────────

    @app.get("/")
    async def landing(request: Request):
        return render(request, "landing.html", user=current_session(request))

    @app.get("/signup")
    async def signup_page(request: Request, invite: str = ""):
        if current_session(request):
            if invite:
                return RedirectResponse(f"/invite/{invite}", status_code=303)
            return RedirectResponse("/app", status_code=303)
        return render(request, "signup.html", invite=invite, form={})

    @app.post("/signup")
    async def signup(request: Request):
        form = await form_of(request)
        invite = form.get("invite", "")
        errors = []
        email = form.get("email", "").lower()
        name = form.get("name", "")
        password = form.get("password", "")
        workspace = form.get("workspace", "")
        if not signup_open and not invite:
            errors.append("Sign-up is invite-only right now — join the waitlist below.")
        if not name:
            errors.append("Tell us your name.")
        if not sec.EMAIL_RE.match(email):
            errors.append("That email doesn't look right.")
        if len(password) < sec.MIN_PASSWORD_LEN:
            errors.append(f"Use at least {sec.MIN_PASSWORD_LEN} characters for your password.")
        if not invite and not workspace:
            errors.append("Name your workspace (usually your company).")
        if not errors and db.one("SELECT 1 FROM users WHERE email = ?", email):
            errors.append("An account with that email already exists — log in instead.")
        if errors:
            return render(
                request, "signup.html", status=400, errors=errors, invite=invite,
                form={"email": email, "name": name, "workspace": workspace},
            )
        user_id = db.run(
            "INSERT INTO users (email, name, password_hash, created_at) VALUES (?, ?, ?, ?)",
            email, name, sec.hash_password(password), now(),
        )
        slug = accept_invite(invite, user_id) if invite else None
        if slug is None:
            slug = create_tenant(workspace or f"{name}'s workspace", user_id)
            target, msg = f"/app/{slug}?welcome=1", "Your workspace is ready."
        else:
            target, msg = f"/app/{slug}", "You've joined the workspace."
        resp = redirect(target, msg)
        start_session(resp, user_id)
        return resp

    @app.get("/login")
    async def login_page(request: Request, next: str = "", invite: str = ""):
        if current_session(request):
            return RedirectResponse(safe_next(next), status_code=303)
        return render(request, "login.html", next=next, invite=invite, form={})

    @app.post("/login")
    async def login(request: Request):
        form = await form_of(request)
        email = form.get("email", "").lower()
        password = form.get("password", "")
        client = request.client.host if request.client else "?"
        if not login_throttle.allow(f"{client}|{email}"):
            return render(
                request, "login.html", status=429, next=form.get("next", ""),
                invite=form.get("invite", ""), form={"email": email},
                errors=["Too many attempts. Wait a few minutes and try again."],
            )
        user = db.one("SELECT * FROM users WHERE email = ?", email)
        if user is None:
            sec.burn_password_check(password)
        if user is None or not sec.verify_password(password, user["password_hash"]):
            return render(
                request, "login.html", status=400, next=form.get("next", ""),
                invite=form.get("invite", ""), form={"email": email},
                errors=["Email or password is incorrect."],
            )
        login_throttle.reset(f"{client}|{email}")
        target = safe_next(form.get("next"))
        if form.get("invite"):
            slug = accept_invite(form["invite"], user["id"])
            if slug:
                target = f"/app/{slug}"
        resp = RedirectResponse(target, status_code=303)
        start_session(resp, user["id"])
        return resp

    @app.post("/logout")
    async def logout(request: Request):
        user = current_session(request)
        if user is not None:
            await form_of(request, user)
            db.run("DELETE FROM sessions WHERE token_hash = ?", user["token_hash"])
        resp = RedirectResponse("/", status_code=303)
        resp.delete_cookie(SESSION_COOKIE)
        return resp

    @app.get("/invite/{token}")
    async def invite_page(request: Request, token: str):
        inv = db.one(
            "SELECT i.role, t.name AS tenant_name, u.name AS inviter FROM invites i "
            "JOIN tenants t ON t.id = i.tenant_id JOIN users u ON u.id = i.created_by "
            "WHERE i.token_hash = ? AND i.accepted_by IS NULL AND i.expires_at > ?",
            sec.token_hash(token), now(),
        )
        user = current_session(request)
        return render(request, "invite.html", user=user, invite=inv, token=token)

    @app.post("/invite/{token}")
    async def invite_accept(request: Request, token: str):
        user = require_user(request)
        await form_of(request, user)
        slug = accept_invite(token, user["id"])
        if slug is None:
            return redirect("/app", "That invite link is invalid or has expired.", "error")
        return redirect(f"/app/{slug}", "You've joined the workspace.")

    @app.post("/feedback")
    async def feedback(request: Request):
        user = current_session(request)
        form = await form_of(request, user)
        client = request.client.host if request.client else "?"
        back = safe_next(form.get("back")) if form.get("back") else "/"
        message = form.get("message", "")[:4000]
        if not message:
            return redirect(back, "Write a few words first.", "error")
        if not feedback_throttle.allow(client):
            return redirect(back, "Thanks — we've got plenty from you for now.", "error")
        tenant_id = None
        if user and form.get("tenant"):
            t = db.membership(user["id"], form["tenant"])
            tenant_id = t["id"] if t else None
        if not user and form.get("email"):
            message = f"[{form['email'][:200]}] {message}"
        db.run(
            "INSERT INTO feedback (tenant_id, user_id, page, sentiment, message, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            tenant_id, user["id"] if user else None, back[:300],
            form.get("sentiment", "")[:20], message, now(),
        )
        return redirect(back, "Thank you — this goes straight to the founder.")

    # ── workspace entry points ──────────────────────────────────────────

    @app.get("/app")
    async def app_home(request: Request):
        user = require_user(request)
        tenants = db.tenants_for_user(user["id"])
        if tenants:
            return RedirectResponse(f"/app/{tenants[0]['slug']}", status_code=303)
        return render(request, "new_workspace.html", user=user)

    @app.get("/app/new")
    async def new_workspace_page(request: Request):
        user = require_user(request)
        return render(request, "new_workspace.html", user=user)

    @app.post("/app/new")
    async def new_workspace(request: Request):
        user = require_user(request)
        form = await form_of(request, user)
        name = form.get("name", "")[:80]
        if not name:
            return redirect("/app/new", "Give the workspace a name.", "error")
        slug = create_tenant(name, user["id"])
        return redirect(f"/app/{slug}?welcome=1", f"Created {name}.")

    @app.post("/account/password")
    async def change_password(request: Request):
        user = require_user(request)
        form = await form_of(request, user)
        back = safe_next(form.get("back"))
        row = db.one("SELECT password_hash FROM users WHERE id = ?", user["id"])
        if not sec.verify_password(form.get("current", ""), row["password_hash"]):
            return redirect(back, "Current password is incorrect.", "error")
        if len(form.get("new", "")) < sec.MIN_PASSWORD_LEN:
            return redirect(back, f"New password needs {sec.MIN_PASSWORD_LEN}+ characters.", "error")
        with db.tx() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (sec.hash_password(form["new"]), user["id"]),
            )
            # Sign out every other session.
            conn.execute(
                "DELETE FROM sessions WHERE user_id = ? AND token_hash != ?",
                (user["id"], user["token_hash"]),
            )
        return redirect(back, "Password changed. Other sessions were signed out.")

    # ── workspace pages ─────────────────────────────────────────────────

    @app.get("/app/{slug}")
    async def overview(request: Request, slug: str, welcome: int = 0):
        user = require_user(request)
        tenant = tenant_for(user, slug)
        graph = runtimes.get(tenant["id"]).graph
        tid = tenant["id"]
        stats = {
            "queries_7d": db.one(
                "SELECT COUNT(*) c FROM queries WHERE tenant_id = ? AND created_at > ?",
                tid, (datetime.now(UTC) - timedelta(days=7)).isoformat(timespec="seconds"),
            )["c"],
            "resolved": db.one(
                "SELECT COUNT(*) c FROM queries WHERE tenant_id = ? AND status = 'ok'", tid
            )["c"],
            "sources": len(graph.sources()) - len(db.disabled_sources(tid)),
            "sources_total": len(graph.sources()),
            "entity_types": len(graph.entity_types()),
            "members": db.one("SELECT COUNT(*) c FROM memberships WHERE tenant_id = ?", tid)["c"],
            "avg_ms": db.one(
                "SELECT CAST(AVG(duration_ms) AS INTEGER) a FROM queries WHERE tenant_id = ? AND status = 'ok'",
                tid,
            )["a"],
        }
        checklist = [
            ("Resolve your first entity", stats["resolved"] > 0, f"/app/{slug}/explore"),
            ("Review the ontology", False, f"/app/{slug}/ontology"),
            (
                "Create an API key for your agent",
                bool(db.one("SELECT 1 FROM api_keys WHERE tenant_id = ?", tid)),
                f"/app/{slug}/api",
            ),
            ("Invite a teammate", stats["members"] > 1, f"/app/{slug}/members"),
        ]
        recent = db.all(
            "SELECT * FROM queries WHERE tenant_id = ? ORDER BY id DESC LIMIT 6", tid
        )
        return render(
            request, "app/overview.html", user=user, tenant=tenant, stats=stats,
            checklist=checklist, recent=recent, welcome=welcome, examples=EXAMPLES,
            nav="overview",
        )

    @app.get("/app/{slug}/explore")
    async def explore(request: Request, slug: str):
        user = require_user(request)
        tenant = tenant_for(user, slug)
        orch = runtimes.get(tenant["id"])
        graph = orch.graph
        entity_types = graph.entity_types()
        params = request.query_params
        entity_type = params.get("entity") or entity_types[0]
        if entity_type not in entity_types:
            raise HTTPException(404, "unknown entity type")
        attrs = graph.attributes_of(entity_type)
        query_attrs = [a for a, d in attrs.items() if d.identifying]
        criteria = {a: params[a].strip() for a in query_attrs if params.get(a, "").strip()}

        result = error = None
        lineage = ""
        graph_els: list[dict] = []
        if criteria:
            result, error = await run_query(
                tenant["id"], entity_type, criteria, actor=user["email"], channel="web"
            )
            if result is not None:
                lineage = render_lineage_tree(result)
                graph_els = entity_graph(result)
        return render(
            request, "app/explore.html", user=user, tenant=tenant, nav="explore",
            entity_types=entity_types, entity_type=entity_type, attrs=attrs,
            query_attrs=query_attrs, criteria=criteria, result=result, error=error,
            lineage=lineage, graph=graph_els, examples=EXAMPLES,
            sources=graph.sources(),
        )

    async def run_query(tenant_id: int, entity_type: str, criteria: dict, *, actor: str, channel: str):
        orch = runtimes.get(tenant_id)
        t0 = time.perf_counter()
        result = error = None
        try:
            result = await orch.get_unified(entity_type, criteria)
            status = "ok"
        except EntityNotFoundError:
            status, error = "not_found", "No records in any enabled source match those criteria."
        except (KeyError, ValueError) as exc:
            status, error = "error", str(exc)
        ms = int((time.perf_counter() - t0) * 1000)
        db.log_query(
            tenant_id, actor=actor, channel=channel, entity_type=entity_type,
            criteria=criteria, request_id=result.request_id if result else None,
            status=status, records=len(result.resolution.cluster_records) if result else 0,
            duration_ms=ms,
        )
        return result, error

    @app.get("/app/{slug}/ontology")
    async def ontology_page(request: Request, slug: str):
        user = require_user(request)
        tenant = tenant_for(user, slug)
        graph = runtimes.get(tenant["id"]).graph
        entities = []
        for name in graph.entity_types():
            source_ids = graph.sources_for(name)
            bindings = {sid: graph.binding_for(name, sid) for sid in source_ids}
            entities.append({
                "name": name,
                "attributes": graph.attributes_of(name),
                "relationships": graph.relationships_of(name),
                "sources": source_ids,
                "bindings": bindings,
            })
        from hubgentic.app import find_ontology_path

        yaml_text = find_ontology_path().read_text()
        return render(
            request, "app/ontology.html", user=user, tenant=tenant, nav="ontology",
            entities=entities, yaml_text=yaml_text,
            graph=ontology_graph(entities, db.disabled_sources(tenant["id"])),
        )

    @app.get("/app/{slug}/sources")
    async def sources_page(request: Request, slug: str):
        user = require_user(request)
        tenant = tenant_for(user, slug)
        graph = runtimes.get(tenant["id"]).graph
        disabled = db.disabled_sources(tenant["id"])
        sources = [
            {
                "id": sid,
                "kind": sdef.kind,
                "description": sdef.description,
                "enabled": sid not in disabled,
                "entities": [e for e in graph.entity_types() if sid in graph.sources_for(e)],
            }
            for sid, sdef in graph.sources().items()
        ]
        return render(
            request, "app/sources.html", user=user, tenant=tenant, nav="sources",
            sources=sources,
        )

    @app.post("/app/{slug}/sources/{source_id}")
    async def toggle_source(request: Request, slug: str, source_id: str):
        user = require_user(request)
        tenant = tenant_for(user, slug)
        require_role(tenant, "owner", "admin")
        form = await form_of(request, user)
        if source_id not in runtimes.get(tenant["id"]).graph.sources():
            raise HTTPException(404, "unknown source")
        enabled = 1 if form.get("enabled") == "1" else 0
        db.run(
            "INSERT INTO tenant_sources (tenant_id, source_id, enabled) VALUES (?, ?, ?) "
            "ON CONFLICT (tenant_id, source_id) DO UPDATE SET enabled = excluded.enabled",
            tenant["id"], source_id, enabled,
        )
        state = "enabled" if enabled else "disabled"
        return redirect(f"/app/{slug}/sources", f"{source_id} {state} for this workspace.")

    @app.get("/app/{slug}/activity")
    async def activity(request: Request, slug: str):
        user = require_user(request)
        tenant = tenant_for(user, slug)
        rows = db.all(
            "SELECT * FROM queries WHERE tenant_id = ? ORDER BY id DESC LIMIT 200",
            tenant["id"],
        )
        return render(
            request, "app/activity.html", user=user, tenant=tenant, nav="activity", rows=rows,
        )

    @app.get("/app/{slug}/api")
    async def api_page(request: Request, slug: str):
        user = require_user(request)
        tenant = tenant_for(user, slug)
        keys = db.all(
            "SELECT k.*, u.name AS creator FROM api_keys k JOIN users u ON u.id = k.created_by "
            "WHERE k.tenant_id = ? ORDER BY k.id DESC",
            tenant["id"],
        )
        new_key = request.cookies.get("hg_newkey")
        resp = render(
            request, "app/api.html", user=user, tenant=tenant, nav="api", keys=keys,
            new_key=new_key, base_url=str(request.base_url).rstrip("/"),
        )
        if new_key:
            resp.delete_cookie("hg_newkey", path=f"/app/{slug}/api")
        return resp

    @app.post("/app/{slug}/api")
    async def create_key(request: Request, slug: str):
        user = require_user(request)
        tenant = tenant_for(user, slug)
        require_role(tenant, "owner", "admin")
        form = await form_of(request, user)
        key, prefix = sec.new_api_key()
        db.run(
            "INSERT INTO api_keys (tenant_id, name, prefix, key_hash, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            tenant["id"], (form.get("name") or "Untitled key")[:60], prefix,
            sec.token_hash(key), user["id"], now(),
        )
        resp = redirect(f"/app/{slug}/api", "Key created. Copy it now — it won't be shown again.")
        # One-time hand-off of the plaintext key to the next page view only.
        resp.set_cookie(
            "hg_newkey", key, max_age=60, httponly=True, samesite="strict",
            secure=secure_cookies, path=f"/app/{slug}/api",
        )
        return resp

    @app.post("/app/{slug}/api/{key_id}/revoke")
    async def revoke_key(request: Request, slug: str, key_id: int):
        user = require_user(request)
        tenant = tenant_for(user, slug)
        require_role(tenant, "owner", "admin")
        await form_of(request, user)
        db.run(
            "UPDATE api_keys SET revoked_at = ? WHERE id = ? AND tenant_id = ? AND revoked_at IS NULL",
            now(), key_id, tenant["id"],
        )
        return redirect(f"/app/{slug}/api", "Key revoked.")

    @app.get("/app/{slug}/members")
    async def members(request: Request, slug: str):
        user = require_user(request)
        tenant = tenant_for(user, slug)
        rows = db.all(
            "SELECT u.id, u.name, u.email, m.role, m.created_at FROM memberships m "
            "JOIN users u ON u.id = m.user_id WHERE m.tenant_id = ? "
            "ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END, u.name",
            tenant["id"],
        )
        pending = db.all(
            "SELECT role, created_at, expires_at FROM invites WHERE tenant_id = ? "
            "AND accepted_by IS NULL AND expires_at > ? ORDER BY created_at DESC",
            tenant["id"], now(),
        )
        invite_url = request.cookies.get("hg_invite")
        resp = render(
            request, "app/members.html", user=user, tenant=tenant, nav="members",
            rows=rows, pending=pending, invite_url=invite_url, roles=ROLES,
        )
        if invite_url:
            resp.delete_cookie("hg_invite", path=f"/app/{slug}/members")
        return resp

    @app.post("/app/{slug}/members/invite")
    async def invite(request: Request, slug: str):
        user = require_user(request)
        tenant = tenant_for(user, slug)
        require_role(tenant, "owner", "admin")
        form = await form_of(request, user)
        role = form.get("role", "member")
        if role not in ("admin", "member"):
            raise HTTPException(400, "invalid role")
        token = sec.new_token()
        db.run(
            "INSERT INTO invites (token_hash, tenant_id, role, created_by, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            sec.token_hash(token), tenant["id"], role, user["id"], now(),
            (datetime.now(UTC) + INVITE_TTL).isoformat(timespec="seconds"),
        )
        url = f"{str(request.base_url).rstrip('/')}/invite/{token}"
        resp = redirect(f"/app/{slug}/members", "Invite link created — valid for 7 days, single use.")
        resp.set_cookie(
            "hg_invite", url, max_age=60, httponly=True, samesite="strict",
            secure=secure_cookies, path=f"/app/{slug}/members",
        )
        return resp

    @app.post("/app/{slug}/members/{member_id}")
    async def update_member(request: Request, slug: str, member_id: int):
        user = require_user(request)
        tenant = tenant_for(user, slug)
        require_role(tenant, "owner", "admin")
        form = await form_of(request, user)
        target = db.one(
            "SELECT role FROM memberships WHERE tenant_id = ? AND user_id = ?",
            tenant["id"], member_id,
        )
        if target is None:
            raise HTTPException(404, "member not found")
        if target["role"] == "owner" and tenant["role"] != "owner":
            raise HTTPException(403, "only an owner can change another owner")
        owners = db.one(
            "SELECT COUNT(*) c FROM memberships WHERE tenant_id = ? AND role = 'owner'",
            tenant["id"],
        )["c"]
        action = form.get("action")
        if action == "remove":
            if target["role"] == "owner" and owners <= 1:
                return redirect(f"/app/{slug}/members", "A workspace needs at least one owner.", "error")
            db.run(
                "DELETE FROM memberships WHERE tenant_id = ? AND user_id = ?",
                tenant["id"], member_id,
            )
            if member_id == user["id"]:
                return redirect("/app", f"You left {tenant['name']}.")
            return redirect(f"/app/{slug}/members", "Member removed.")
        role = form.get("role", "")
        if role not in ROLES:
            raise HTTPException(400, "invalid role")
        if role == "owner" and tenant["role"] != "owner":
            raise HTTPException(403, "only an owner can grant ownership")
        if target["role"] == "owner" and role != "owner" and owners <= 1:
            return redirect(f"/app/{slug}/members", "A workspace needs at least one owner.", "error")
        db.run(
            "UPDATE memberships SET role = ? WHERE tenant_id = ? AND user_id = ?",
            role, tenant["id"], member_id,
        )
        return redirect(f"/app/{slug}/members", "Role updated.")

    @app.get("/app/{slug}/settings")
    async def settings_page(request: Request, slug: str):
        user = require_user(request)
        tenant = tenant_for(user, slug)
        return render(request, "app/settings.html", user=user, tenant=tenant, nav="settings")

    @app.post("/app/{slug}/settings")
    async def settings(request: Request, slug: str):
        user = require_user(request)
        tenant = tenant_for(user, slug)
        require_role(tenant, "owner", "admin")
        form = await form_of(request, user)
        name = form.get("name", "")[:80]
        if not name:
            return redirect(f"/app/{slug}/settings", "Name can't be empty.", "error")
        db.run("UPDATE tenants SET name = ? WHERE id = ?", name, tenant["id"])
        return redirect(f"/app/{slug}/settings", "Workspace renamed.")

    # ── staff console: everything you need to read early feedback ───────

    @app.get("/admin")
    async def admin(request: Request):
        user = require_user(request)
        if user["email"].lower() not in admin_emails:
            raise HTTPException(404)
        return render(
            request, "admin.html", user=user,
            feedback=db.all(
                "SELECT f.*, u.email, t.name AS tenant_name FROM feedback f "
                "LEFT JOIN users u ON u.id = f.user_id LEFT JOIN tenants t ON t.id = f.tenant_id "
                "ORDER BY f.id DESC LIMIT 300"
            ),
            signups=db.all(
                "SELECT u.email, u.name, u.created_at, "
                "(SELECT COUNT(*) FROM memberships m WHERE m.user_id = u.id) AS workspaces "
                "FROM users u ORDER BY u.id DESC LIMIT 300"
            ),
            usage=db.all(
                "SELECT t.name, t.slug, t.created_at, COUNT(q.id) AS queries, MAX(q.created_at) AS last "
                "FROM tenants t LEFT JOIN queries q ON q.tenant_id = t.id "
                "GROUP BY t.id ORDER BY queries DESC"
            ),
        )

    # ── REST API (API-key auth, tenant derived from the key) ────────────

    def api_tenant(request: Request):
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            raise HTTPException(401, "missing bearer API key", {"WWW-Authenticate": "Bearer"})
        row = db.one(
            "SELECT k.id, k.prefix, t.id AS tenant_id FROM api_keys k "
            "JOIN tenants t ON t.id = k.tenant_id WHERE k.key_hash = ? AND k.revoked_at IS NULL",
            sec.token_hash(auth[7:].strip()),
        )
        if row is None:
            raise HTTPException(401, "invalid or revoked API key", {"WWW-Authenticate": "Bearer"})
        db.run("UPDATE api_keys SET last_used_at = ? WHERE id = ?", now(), row["id"])
        return row

    @app.get("/api/v1/ontology")
    async def api_ontology(request: Request):
        key = api_tenant(request)
        graph = runtimes.get(key["tenant_id"]).graph
        return {
            "entities": {
                name: {
                    "attributes": {a: d.model_dump(exclude_none=True) for a, d in graph.attributes_of(name).items()},
                    "relationships": list(graph.relationships_of(name)),
                    "sources": graph.sources_for(name),
                }
                for name in graph.entity_types()
            }
        }

    @app.post("/api/v1/unified")
    async def api_unified(request: Request):
        key = api_tenant(request)
        try:
            body = await request.json()
            entity_type = body["entity_type"]
            criteria = {str(k): str(v) for k, v in dict(body["criteria"]).items()}
        except (ValueError, KeyError, TypeError):
            raise HTTPException(422, 'body must be {"entity_type": str, "criteria": {attr: value}}')
        result, error = await run_query(
            key["tenant_id"], entity_type, criteria, actor=f"key:{key['prefix']}…", channel="api"
        )
        if result is None:
            return JSONResponse({"detail": error}, status_code=404)
        return JSONResponse(json.loads(result.model_dump_json()))

    @app.get("/api/v1/lineage/{request_id}")
    async def api_lineage(request: Request, request_id: str):
        key = api_tenant(request)
        unified = runtimes.get(key["tenant_id"]).explain(request_id)
        if unified is None:
            raise HTTPException(404, "unknown or expired request_id (cache TTL 15 min)")
        return {"request_id": request_id, "rendered": render_lineage_tree(unified)}

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    return app


def _ago(iso: str | None) -> str:
    if not iso:
        return "never"
    delta = datetime.now(UTC) - datetime.fromisoformat(iso)
    s = int(delta.total_seconds())
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{s // 60}m ago"
    if s < 86400:
        return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"


def main() -> None:
    import uvicorn

    uvicorn.run(
        "hubgentic.web.app:create_app",
        factory=True,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
    )
