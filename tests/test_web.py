"""Web app: auth, tenant isolation, roles, CSRF, API keys, governance."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from hubgentic.web.app import create_app

PASSWORD = "correct-horse-battery"


@pytest.fixture
def app(tmp_path):
    return create_app(
        tmp_path / "test.db", secure_cookies=False, admin_emails={"founder@example.com"},
        signup_open=True, simulated_latency_s=0.0,
    )


def client(app) -> TestClient:
    return TestClient(app, base_url="http://testserver")


def signup(c: TestClient, email: str, workspace: str = "Acme Bank", invite: str = "") -> str:
    r = c.post(
        "/signup",
        data={"name": email.split("@")[0], "email": email, "password": PASSWORD,
              "workspace": workspace, "invite": invite},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    return r.headers["location"]


def csrf(c: TestClient, path: str) -> str:
    html = c.get(path).text
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def slug_of(location: str) -> str:
    return location.split("/")[2].split("?")[0]


def test_signup_creates_workspace_and_session(app):
    c = client(app)
    loc = signup(c, "ana@example.com")
    assert loc.startswith("/app/acme-bank")
    r = c.get(loc)
    assert r.status_code == 200
    assert "Welcome to Acme Bank" in r.text


def test_duplicate_email_and_weak_password_rejected(app):
    c = client(app)
    signup(c, "ana@example.com")
    c2 = client(app)
    r = c2.post("/signup", data={"name": "x", "email": "ANA@example.com", "password": PASSWORD, "workspace": "w"})
    assert r.status_code == 400 and "already exists" in r.text
    r = c2.post("/signup", data={"name": "x", "email": "b@example.com", "password": "short", "workspace": "w"})
    assert r.status_code == 400 and "10 characters" in r.text


def test_login_logout_and_bad_password(app):
    c = client(app)
    signup(c, "ana@example.com")
    c2 = client(app)
    r = c2.post("/login", data={"email": "ana@example.com", "password": "wrong-password"})
    assert r.status_code == 400
    r = c2.post("/login", data={"email": "ana@example.com", "password": PASSWORD}, follow_redirects=False)
    assert r.status_code == 303
    token = csrf(c2, "/app/acme-bank")
    c2.post("/logout", data={"csrf": token})
    r = c2.get("/app/acme-bank", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_unauthenticated_redirects_to_login(app):
    r = client(app).get("/app/anything/explore", follow_redirects=False)
    assert r.status_code == 303 and "/login?next=" in r.headers["location"]


def test_tenant_isolation(app):
    a, b = client(app), client(app)
    slug_a = slug_of(signup(a, "ana@example.com", "Alpha"))
    slug_b = slug_of(signup(b, "bob@example.com", "Beta"))
    for path in ("", "/explore", "/members", "/api", "/activity", "/settings"):
        assert b.get(f"/app/{slug_a}{path}").status_code == 404
    token_b = csrf(b, f"/app/{slug_b}")
    # Bob's valid CSRF token doesn't let him act inside Alpha.
    r = b.post(f"/app/{slug_a}/sources/crm", data={"csrf": token_b, "enabled": "0"})
    assert r.status_code == 404
    # Ana's audit log never shows Bob's queries.
    b.get(f"/app/{slug_b}/explore?legal_name=Lucia+Bianchi")
    assert "Lucia" not in a.get(f"/app/{slug_a}/activity").text


def test_csrf_required_and_cross_origin_rejected(app):
    c = client(app)
    slug = slug_of(signup(c, "ana@example.com"))
    assert c.post(f"/app/{slug}/settings", data={"name": "Hacked"}).status_code == 403
    r = c.post("/login", data={"email": "x@y.z", "password": "p"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_explorer_resolves_and_logs(app):
    c = client(app)
    slug = slug_of(signup(c, "ana@example.com"))
    r = c.get(f"/app/{slug}/explore?legal_name=Lucia+Bianchi")
    assert r.status_code == 200
    assert "fuzzy.name_dob_email" in r.text
    assert "BNCLCU85M41F205X" in r.text
    assert "resolved" in c.get(f"/app/{slug}/activity").text


def test_invite_flow_and_member_cannot_admin(app):
    owner = client(app)
    slug = slug_of(signup(owner, "ana@example.com"))
    token = csrf(owner, f"/app/{slug}/members")
    html = owner.post(f"/app/{slug}/members/invite", data={"csrf": token, "role": "member"}).text
    invite_token = re.search(r'value="http://testserver/invite/([^"]+)"', html).group(1)

    member = client(app)
    loc = signup(member, "max@example.com", invite=invite_token)
    assert loc == f"/app/{slug}"
    assert member.get(f"/app/{slug}").status_code == 200

    # Invite links are single-use.
    third = client(app)
    r = third.post("/signup", data={"name": "z", "email": "z@example.com", "password": PASSWORD,
                                     "workspace": "Own", "invite": invite_token}, follow_redirects=False)
    assert slug_of(r.headers["location"]) != slug

    m_token = csrf(member, f"/app/{slug}")
    assert member.post(f"/app/{slug}/api", data={"csrf": m_token, "name": "k"}).status_code == 403
    assert member.post(f"/app/{slug}/sources/crm", data={"csrf": m_token, "enabled": "0"}).status_code == 403
    assert member.post(f"/app/{slug}/members/invite", data={"csrf": m_token}).status_code == 403


def test_last_owner_cannot_leave(app):
    c = client(app)
    slug = slug_of(signup(c, "ana@example.com"))
    token = csrf(c, f"/app/{slug}/members")
    html = c.get(f"/app/{slug}/members").text
    uid = re.search(rf'/app/{slug}/members/(\d+)', html).group(1)
    r = c.post(f"/app/{slug}/members/{uid}", data={"csrf": token, "action": "remove"})
    assert "at least one owner" in r.text
    assert c.get(f"/app/{slug}").status_code == 200


def test_api_key_scoped_to_tenant_and_revocable(app):
    c = client(app)
    slug = slug_of(signup(c, "ana@example.com"))
    token = csrf(c, f"/app/{slug}/api")
    html = c.post(f"/app/{slug}/api", data={"csrf": token, "name": "agent"}).text  # one-time display
    key = re.search(r'value="(hg_live_[^"]+)"', html).group(1)
    assert key not in c.get(f"/app/{slug}/api").text  # never shown again

    api = client(app)
    assert api.post("/api/v1/unified", json={}).status_code == 401
    h = {"Authorization": f"Bearer {key}"}
    r = api.post("/api/v1/unified", headers=h, json={"entity_type": "Counterparty", "criteria": {"national_tax_code": "IT01234567890"}})
    assert r.status_code == 200
    body = r.json()
    assert body["fields"]["legal_name"][0]["provenance"]["source"] == "core_banking"
    assert api.get(f"/api/v1/lineage/{body['request_id']}", headers=h).status_code == 200

    # Another tenant's key can't read this tenant's lineage cache.
    other = client(app)
    oslug = slug_of(signup(other, "bob@example.com", "Beta"))
    otoken = csrf(other, f"/app/{oslug}/api")
    ohtml = other.post(f"/app/{oslug}/api", data={"csrf": otoken, "name": "x"}).text
    okey = re.search(r'value="(hg_live_[^"]+)"', ohtml).group(1)
    r = api.get(f"/api/v1/lineage/{body['request_id']}", headers={"Authorization": f"Bearer {okey}"})
    assert r.status_code == 404

    kid = re.search(rf'/app/{slug}/api/(\d+)/revoke', c.get(f"/app/{slug}/api").text).group(1)
    c.post(f"/app/{slug}/api/{kid}/revoke", data={"csrf": token})
    assert api.get("/api/v1/ontology", headers=h).status_code == 401


def test_source_governance_is_per_tenant(app):
    a, b = client(app), client(app)
    slug_a = slug_of(signup(a, "ana@example.com", "Alpha"))
    slug_b = slug_of(signup(b, "bob@example.com", "Beta"))
    a.post(f"/app/{slug_a}/sources/crm", data={"csrf": csrf(a, f"/app/{slug_a}/sources"), "enabled": "0"})
    ra = a.get(f"/app/{slug_a}/explore?legal_name=Lucia+Bianchi").text
    rb = b.get(f"/app/{slug_b}/explore?legal_name=Lucia+Bianchi").text
    assert "denied by policy" in ra and "001A000003" not in ra
    assert "001A000003" in rb


def test_feedback_and_admin_console(app):
    anon = client(app)
    anon.post("/feedback", data={"message": "Need Snowflake", "email": "lead@bank.com", "back": "/"})
    founder = client(app)
    signup(founder, "founder@example.com")
    assert "Need Snowflake" in founder.get("/admin").text
    nobody = client(app)
    signup(nobody, "rando@example.com", "Rando")
    assert nobody.get("/admin").status_code == 404


def test_hsts_only_when_secure(tmp_path, app):
    assert "strict-transport-security" not in client(app).get("/").headers
    secure = create_app(tmp_path / "s.db", secure_cookies=True, simulated_latency_s=0.0)
    hsts = TestClient(secure, base_url="https://testserver").get("/").headers["strict-transport-security"]
    assert "max-age=31536000" in hsts


def test_graph_payloads(app):
    import json

    c = client(app)
    slug = slug_of(signup(c, "ana@example.com"))

    def elements(html: str, gid: str) -> list[dict]:
        raw = re.search(rf'<script id="{gid}" type="application/json">(.*?)</script>', html, re.S).group(1)
        return [e["data"] for e in json.loads(raw)]

    els = elements(c.get(f"/app/{slug}/explore?legal_name=Lucia+Bianchi").text, "entity-graph")
    kinds = {e["kind"] for e in els}
    assert {"entity", "record", "member", "match"} <= kinds
    ids = {e["id"] for e in els}
    assert all(e["source"] in ids and e["target"] in ids for e in els if "target" in e)

    onto = elements(c.get(f"/app/{slug}/ontology").text, "ontology-graph")
    assert {"entity", "attribute", "source", "binding", "rel"} <= {e["kind"] for e in onto}
