"""Admin cockpit over a real PostGIS database.

User management protections (step-up, last admin, self-actions, optimistic
locking, session revocation, forced password change), audit filters/export,
cockpit metrics checked against SQL, RBAC matrix and API docs exposure.
"""

import asyncio
import csv
import io
import secrets
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_action
from app.core.security import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.users.model import User

# Generated per run: no credential-like literal lives in the repository.
PASSWORD = secrets.token_urlsafe(18)
NEW_PASSWORD = secrets.token_urlsafe(18)
WRONG_PASSWORD = secrets.token_urlsafe(18)
REASON = "rotina de teste automatizado"


@pytest.fixture
async def admin_db(geo_engine):
    # Session-scoped database shared with other modules: keep the IBGE import
    # audit entry and the boundaries; references to users are ON DELETE SET NULL.
    async with geo_engine.begin() as conn:
        await conn.execute(text("DELETE FROM audit_logs WHERE action <> 'jurisdictions.imported'"))
        await conn.execute(text("TRUNCATE orbital_detections, ingestion_runs"))
        await conn.execute(text("DELETE FROM users"))

    async def _db():
        async with AsyncSession(geo_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = _db
    return geo_engine


async def _user(engine, role: str, *, email: str | None = None, active: bool = True) -> User:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        user = User(
            name=f"Pessoa {role}",
            email=email or f"{role}.{uuid.uuid4().hex[:8]}@example.org",
            password_hash=hash_password(PASSWORD),
            role=role,
            is_active=active,
        )
        session.add(user)
        await session.commit()
        return user


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role)}"}


async def _scalar(engine, sql: str, **params):
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).scalar()


async def _fresh(client, admin, user_id) -> dict:
    response = await client.get(f"/api/v1/admin/users/{user_id}", headers=_auth(admin))
    assert response.status_code == 200
    return response.json()


def _guard(version: int, password: str = PASSWORD) -> dict:
    return {"expected_version": version, "confirm_password": password, "reason": REASON}


ADMIN_GETS = [
    "/api/v1/admin/overview",
    "/api/v1/admin/sources",
    "/api/v1/admin/ingestion-runs",
    "/api/v1/admin/permissions",
    "/api/v1/admin/settings",
    "/api/v1/admin/openapi.json",
    "/api/v1/admin/users",
    "/api/v1/admin/audit-logs",
    "/api/v1/admin/audit-logs/export",
]


@pytest.mark.parametrize("role", ["campo", "gestor", "orgao"])
async def test_admin_endpoints_deny_every_non_admin_role(admin_db, client, role):
    user = await _user(admin_db, role)
    for path in ADMIN_GETS:
        response = await client.get(path, headers=_auth(user))
        assert response.status_code == 403, path
    anonymous = await client.get("/api/v1/admin/overview")
    assert anonymous.status_code == 401


async def test_create_user_forces_password_change_and_never_echoes_secrets(admin_db, client):
    admin = await _user(admin_db, "admin")
    body = {
        "name": "Maria Souza",
        "email": "Maria.Souza@Example.org",
        "role": "gestor",
        "temporary_password": PASSWORD,
        "reason": "nova analista",
    }
    created = await client.post("/api/v1/admin/users", json=body, headers=_auth(admin))
    assert created.status_code == 201
    data = created.json()
    assert (data["email"], data["must_change_password"], data["row_version"]) == (
        "maria.souza@example.org",
        True,
        1,
    )
    assert not {"password", "password_hash", "temporary_password"} & data.keys()
    assert PASSWORD not in created.text

    duplicate = await client.post(
        "/api/v1/admin/users",
        json={**body, "email": "MARIA.SOUZA@example.org"},
        headers=_auth(admin),
    )
    assert duplicate.status_code == 409

    audit = await client.get(
        "/api/v1/admin/audit-logs", params={"action": "user.created"}, headers=_auth(admin)
    )
    assert audit.json()["total"] == 1
    assert PASSWORD not in audit.text


async def test_forced_password_change_gates_the_api_and_rotates_the_session(admin_db, client):
    admin = await _user(admin_db, "admin")
    body = {"name": "Novo", "email": "novo@example.org", "role": "gestor"}
    await client.post(
        "/api/v1/admin/users", json={**body, "temporary_password": PASSWORD}, headers=_auth(admin)
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": "NOVO@example.org", "password": PASSWORD}
    )
    assert login.status_code == 200
    first = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert login.json()["user"]["must_change_password"] is True

    assert (await client.get("/api/v1/auth/me", headers=first)).status_code == 200
    blocked = await client.get("/api/v1/incidents", headers=first)
    assert blocked.status_code == 403

    wrong = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": WRONG_PASSWORD, "new_password": NEW_PASSWORD},
        headers=first,
    )
    assert wrong.status_code == 403
    changed = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=first,
    )
    assert changed.status_code == 200
    second = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert (await client.get("/api/v1/auth/me", headers=first)).status_code == 401
    assert (await client.get("/api/v1/incidents", headers=second)).status_code == 200


async def test_profile_update_uses_optimistic_locking(admin_db, client):
    admin = await _user(admin_db, "admin")
    target = await _user(admin_db, "campo")
    url = f"/api/v1/admin/users/{target.id}"
    ok = await client.patch(
        url, json={"expected_version": 1, "name": "Nome Novo"}, headers=_auth(admin)
    )
    assert (ok.status_code, ok.json()["row_version"]) == (200, 2)
    stale = await client.patch(
        url, json={"expected_version": 1, "name": "Outro Nome"}, headers=_auth(admin)
    )
    assert stale.status_code == 409
    assert (await _fresh(client, admin, target.id))["name"] == "Nome Novo"
    bad_team = await client.patch(
        url, json={"expected_version": 2, "team_id": str(uuid.uuid4())}, headers=_auth(admin)
    )
    assert bad_team.status_code == 422


async def test_role_change_requires_step_up_and_revokes_sessions(admin_db, client):
    admin = await _user(admin_db, "admin")
    target = await _user(admin_db, "campo")
    target_token = _auth(target)
    assert (await client.get("/api/v1/auth/me", headers=target_token)).status_code == 200
    url = f"/api/v1/admin/users/{target.id}/role"

    denied = await client.post(
        url, json={**_guard(1, WRONG_PASSWORD), "role": "gestor"}, headers=_auth(admin)
    )
    assert denied.status_code == 403
    assert (await _fresh(client, admin, target.id))["role"] == "campo"
    assert (
        await _scalar(
            admin_db, "SELECT count(*) FROM audit_logs WHERE action = 'user.role_change.denied'"
        )
        == 1
    )

    changed = await client.post(url, json={**_guard(1), "role": "gestor"}, headers=_auth(admin))
    assert (changed.status_code, changed.json()["role"]) == (200, "gestor")
    assert (await client.get("/api/v1/auth/me", headers=target_token)).status_code == 401
    meta = await _scalar(
        admin_db, "SELECT metadata_json FROM audit_logs WHERE action = 'user.role_changed'"
    )
    assert (meta["from"], meta["to"], meta["reason"]) == ("campo", "gestor", REASON)


async def test_reason_is_mandatory_for_sensitive_actions(admin_db, client):
    admin = await _user(admin_db, "admin")
    target = await _user(admin_db, "campo")
    response = await client.post(
        f"/api/v1/admin/users/{target.id}/deactivate",
        json={"expected_version": 1, "confirm_password": PASSWORD},
        headers=_auth(admin),
    )
    assert response.status_code == 422


async def test_admin_cannot_demote_deactivate_or_reset_itself(admin_db, client):
    admin = await _user(admin_db, "admin")
    await _user(admin_db, "admin")  # another admin: the block is about "self"
    base = f"/api/v1/admin/users/{admin.id}"
    role = await client.post(
        f"{base}/role", json={**_guard(1), "role": "gestor"}, headers=_auth(admin)
    )
    off = await client.post(f"{base}/deactivate", json=_guard(1), headers=_auth(admin))
    reset = await client.post(
        f"{base}/reset-password",
        json={**_guard(1), "temporary_password": NEW_PASSWORD},
        headers=_auth(admin),
    )
    assert [role.status_code, off.status_code, reset.status_code] == [409, 409, 409]
    assert (await _fresh(client, admin, admin.id))["is_active"] is True
    causes = await _scalar(
        admin_db,
        "SELECT array_agg(metadata_json->>'cause' ORDER BY action) FROM audit_logs"
        " WHERE action LIKE '%.denied'",
    )
    assert causes == ["self", "self", "self"]


async def test_last_legitimate_admin_cannot_be_removed(admin_db, client):
    # The only legitimate admin is the target; the actor is a demo-seed admin,
    # which never counts as a legitimate administrator.
    from seed.demo_users import DEMO_EMAILS

    demo_email = sorted(e for e in DEMO_EMAILS if e.startswith("admin"))[0]
    demo_admin = await _user(admin_db, "admin", email=demo_email)
    real_admin = await _user(admin_db, "admin")
    base = f"/api/v1/admin/users/{real_admin.id}"
    demote = await client.post(
        f"{base}/role", json={**_guard(1), "role": "gestor"}, headers=_auth(demo_admin)
    )
    deactivate = await client.post(f"{base}/deactivate", json=_guard(1), headers=_auth(demo_admin))
    assert (demote.status_code, deactivate.status_code) == (409, 409)
    assert "último administrador" in demote.json()["detail"]
    state = await _fresh(client, demo_admin, real_admin.id)
    assert (state["role"], state["is_active"]) == ("admin", True)


async def test_concurrent_mutual_demotion_keeps_one_admin(admin_db, client):
    first = await _user(admin_db, "admin")
    second = await _user(admin_db, "admin")

    async def demote(actor, target):
        return await client.post(
            f"/api/v1/admin/users/{target.id}/role",
            json={**_guard(1), "role": "gestor"},
            headers=_auth(actor),
        )

    results = await asyncio.gather(demote(first, second), demote(second, first))
    codes = sorted(r.status_code for r in results)
    assert codes[0] == 200
    assert codes[1] in (403, 409)  # lost the role while waiting, or last admin
    remaining = await _scalar(
        admin_db, "SELECT count(*) FROM users WHERE role = 'admin' AND is_active"
    )
    assert remaining == 1


async def test_concurrent_edits_with_the_same_version_conflict(admin_db, client):
    admin = await _user(admin_db, "admin")
    target = await _user(admin_db, "campo")

    async def rename(name):
        return await client.patch(
            f"/api/v1/admin/users/{target.id}",
            json={"expected_version": 1, "name": name},
            headers=_auth(admin),
        )

    results = await asyncio.gather(rename("Nome A"), rename("Nome B"))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert await _scalar(admin_db, "SELECT row_version FROM users WHERE id = :i", i=target.id) == 2


async def test_deactivated_account_cannot_log_in_and_loses_its_session(admin_db, client):
    admin = await _user(admin_db, "admin")
    target = await _user(admin_db, "gestor", email="alvo@example.org")
    session = _auth(target)
    off = await client.post(
        f"/api/v1/admin/users/{target.id}/deactivate", json=_guard(1), headers=_auth(admin)
    )
    assert (off.status_code, off.json()["is_active"]) == (200, False)
    assert (await client.get("/api/v1/auth/me", headers=session)).status_code == 401

    inactive = await client.post(
        "/api/v1/auth/login", json={"email": "alvo@example.org", "password": PASSWORD}
    )
    unknown = await client.post(
        "/api/v1/auth/login", json={"email": "ninguem@example.org", "password": PASSWORD}
    )
    # Same answer for inactive and unknown accounts (no enumeration).
    assert (inactive.status_code, inactive.json()) == (unknown.status_code, unknown.json())
    assert inactive.status_code == 401

    on = await client.post(
        f"/api/v1/admin/users/{target.id}/activate", json=_guard(2), headers=_auth(admin)
    )
    assert on.status_code == 200
    again = await client.post(
        "/api/v1/auth/login", json={"email": "alvo@example.org", "password": PASSWORD}
    )
    assert again.status_code == 200


async def test_password_reset_forces_change_and_revokes(admin_db, client):
    admin = await _user(admin_db, "admin")
    target = await _user(admin_db, "campo", email="campo.reset@example.org")
    session = _auth(target)
    reset = await client.post(
        f"/api/v1/admin/users/{target.id}/reset-password",
        json={**_guard(1), "temporary_password": NEW_PASSWORD},
        headers=_auth(admin),
    )
    assert (reset.status_code, reset.json()["must_change_password"]) == (200, True)
    assert NEW_PASSWORD not in reset.text
    assert (await client.get("/api/v1/auth/me", headers=session)).status_code == 401
    old = await client.post(
        "/api/v1/auth/login", json={"email": "campo.reset@example.org", "password": PASSWORD}
    )
    new = await client.post(
        "/api/v1/auth/login", json={"email": "campo.reset@example.org", "password": NEW_PASSWORD}
    )
    assert (old.status_code, new.status_code) == (401, 200)


async def test_user_list_paginates_and_filters(admin_db, client):
    admin = await _user(admin_db, "admin")
    for i in range(5):
        await _user(admin_db, "campo", email=f"campo{i}@example.org")
    await _user(admin_db, "gestor", email="gestora.inativa@example.org", active=False)
    headers = _auth(admin)
    page = await client.get("/api/v1/admin/users", params={"size": 2, "page": 2}, headers=headers)
    assert (page.json()["total"], page.json()["pages"], len(page.json()["items"])) == (7, 4, 2)
    campo = await client.get("/api/v1/admin/users", params={"role": "campo"}, headers=headers)
    assert campo.json()["total"] == 5
    inactive = await client.get(
        "/api/v1/admin/users", params={"status": "inactive"}, headers=headers
    )
    assert [u["email"] for u in inactive.json()["items"]] == ["gestora.inativa@example.org"]
    search = await client.get("/api/v1/admin/users", params={"q": "GESTORA"}, headers=headers)
    assert search.json()["total"] == 1
    assert all("password_hash" not in u for u in page.json()["items"])


async def test_audit_filters_sanitizes_and_exports(admin_db, client):
    admin = await _user(admin_db, "admin")
    target = await _user(admin_db, "campo")
    async with AsyncSession(admin_db) as session:
        await log_action(
            session,
            "=HYPERLINK(evil)",
            "User",
            target.id,
            actor_name=admin.name,
            actor_id=admin.id,
            metadata={"token": "abc", "nested": {"api_key": "x"}, "ok": 1},
        )
        await session.commit()
    headers = _auth(admin)
    involving = await client.get(
        "/api/v1/admin/audit-logs", params={"involving_user": str(target.id)}, headers=headers
    )
    item = involving.json()["items"][0]
    assert item["metadata_json"] == {
        "token": "[omitido]",
        "nested": {"api_key": "[omitido]"},
        "ok": 1,
    }

    history = await client.get(f"/api/v1/admin/users/{target.id}/audit", headers=headers)
    assert history.json()["total"] == 1
    future = await client.get(
        "/api/v1/admin/audit-logs", params={"from": "2999-01-01T00:00:00Z"}, headers=headers
    )
    assert future.json()["total"] == 0

    export = await client.get("/api/v1/admin/audit-logs/export", headers=headers)
    assert export.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(export.text)))
    assert rows[1][1] == "'=HYPERLINK(evil)"
    assert "abc" not in export.text
    assert (
        await _scalar(admin_db, "SELECT count(*) FROM audit_logs WHERE action = 'audit.exported'")
        == 1
    )


async def test_overview_reports_real_counts_and_declares_missing_metrics(admin_db, client):
    admin = await _user(admin_db, "admin")
    await _user(admin_db, "campo", active=False)
    response = await client.get("/api/v1/admin/overview", headers=_auth(admin))
    assert response.status_code == 200
    data = response.json()
    assert data["database"]["status"] == "connected"
    assert data["database"]["postgis_version"]
    assert data["users"]["active"] == 1
    assert data["users"]["inactive"] == 1
    assert data["data"]["municipalities_monitored"] == await _scalar(
        admin_db, "SELECT count(*) FROM jurisdictions WHERE level = 'municipality'"
    )
    assert data["data"]["detections_total"] == await _scalar(
        admin_db, "SELECT count(*) FROM orbital_detections"
    )
    assert data["worker"]["state"] == "no_evidence"  # no scheduled run recorded
    assert data["unavailable_metrics"]
    for absent in ("cpu", "memory", "uptime_percent", "requests_per_minute"):
        assert absent not in response.text.lower().replace("cpu, memória", "")


async def test_sources_and_settings_never_expose_secrets(admin_db, client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "nasa_firms_map_key", "chave-que-nao-pode-vazar")
    admin = await _user(admin_db, "admin")
    sources = await client.get("/api/v1/admin/sources", headers=_auth(admin))
    settings = await client.get("/api/v1/admin/settings", headers=_auth(admin))
    for response in (sources, settings):
        assert response.status_code == 200
        assert "chave-que-nao-pode-vazar" not in response.text
        assert get_settings().jwt_secret_key not in response.text
    firms = next(s for s in sources.json()["sources"] if s["source"] == "NASA_FIRMS")
    assert firms["configuration"]["configured"] is True
    assert firms["configuration"]["homologated"] is False
    assert "database_url" not in settings.text


async def test_ingestion_runs_filter_and_detail(admin_db, client):
    admin = await _user(admin_db, "admin")
    async with admin_db.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO ingestion_runs (id, source, product, trigger, status, started_at,"
                " finished_at, records_fetched, records_valid, records_inserted)"
                " VALUES (gen_random_uuid(), 'INPE_QUEIMADAS', 'diario', 'schedule', 'ok', now(),"
                " now(), 3, 3, 3), (gen_random_uuid(), 'NASA_FIRMS', 'VIIRS_SNPP_NRT',"
                " 'manual', 'disabled', now(), now(), 0, 0, 0)"
            )
        )
    headers = _auth(admin)
    all_runs = await client.get("/api/v1/admin/ingestion-runs", headers=headers)
    assert all_runs.json()["total"] == 2
    inpe = await client.get(
        "/api/v1/admin/ingestion-runs",
        params={"source": "INPE_QUEIMADAS", "status": "ok", "trigger": "schedule"},
        headers=headers,
    )
    assert inpe.json()["total"] == 1
    run_id = inpe.json()["items"][0]["id"]
    detail = await client.get(f"/api/v1/admin/ingestion-runs/{run_id}", headers=headers)
    assert detail.json()["records_inserted"] == 3
    missing = await client.get(f"/api/v1/admin/ingestion-runs/{uuid.uuid4()}", headers=headers)
    assert missing.status_code == 404
    overview = await client.get("/api/v1/admin/overview", headers=headers)
    assert overview.json()["worker"]["state"] == "recent_runs"


async def test_permission_matrix_matches_the_mounted_api(admin_db, client):
    admin = await _user(admin_db, "admin")
    data = (await client.get("/api/v1/admin/permissions", headers=_auth(admin))).json()
    matrix = {(e["method"], e["path"]): e["access"] for e in data["endpoints"]}
    operations = {
        (method.upper(), path) for path, item in app.openapi()["paths"].items() for method in item
    }
    assert set(matrix) == operations
    admin_paths = [p for (_, p) in matrix if p.startswith("/api/v1/admin/") and "stats" not in p]
    assert admin_paths
    assert all(matrix[(m, p)] == "admin" for (m, p) in matrix if p in admin_paths)
    assert matrix[("POST", "/api/v1/auth/login")] == "público"
    assert matrix[("GET", "/api/v1/auth/me")] == "autenticado"


async def test_operational_environment_hides_public_docs(admin_db, monkeypatch):
    import app.main as main

    staging = main.settings.model_copy(update={"app_env": "staging", "api_docs_public": True})
    assert staging.docs_public is False  # cannot be forced on in staging/production
    monkeypatch.setattr(main, "settings", staging)
    hardened = main.create_app()
    hardened.dependency_overrides = app.dependency_overrides
    admin = await _user(admin_db, "admin")
    gestor = await _user(admin_db, "gestor")
    async with AsyncClient(transport=ASGITransport(app=hardened), base_url="http://t") as c:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert (await c.get(path)).status_code == 404, path
        spec = await c.get("/api/v1/admin/openapi.json", headers=_auth(admin))
        assert spec.status_code == 200
        assert spec.json()["info"]["title"] == "IGNIS Orbital API"
        assert (await c.get("/api/v1/admin/openapi.json", headers=_auth(gestor))).status_code == 403
        assert (await c.get("/api/v1/admin/openapi.json")).status_code == 401


def test_development_keeps_public_docs_by_default():
    from app.main import settings

    assert settings.docs_public is True
    assert app.docs_url == "/docs"


def test_openapi_has_professional_metadata_and_no_academic_text():
    spec = app.openapi()
    assert spec["info"]["contact"]["name"] == "Andrade Systems"
    blob = str(spec).lower()
    for term in ("fiap", "global solution", "acadêmico", "rm561257", "rm566427"):
        assert term not in blob
    tags = {t["name"] for t in spec["tags"]}
    used = {t for item in spec["paths"].values() for op in item.values() for t in op["tags"]}
    assert used <= tags
