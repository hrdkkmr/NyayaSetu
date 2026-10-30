from __future__ import annotations

import httpx

from tests.conftest import make_admin, register


async def test_users_cannot_access_each_others_cases(client: httpx.AsyncClient) -> None:
    alice = await register(client)
    case = (await alice.post("/cases", json={"language": "en"})).json()["case"]
    client.cookies.clear()
    bob = await register(client)
    for url in (f"/cases/{case['id']}", f"/cases/{case['id']}/messages", f"/cases/{case['id']}/uploads",
                f"/cases/{case['id']}/drafts", f"/cases/{case['id']}/research", f"/cases/{case['id']}/filing"):
        resp = await bob.get(url)
        assert resp.status_code == 404, url  # 404, not 403: existence is not revealed
    send = await bob.post(f"/cases/{case['id']}/messages", json={"text": "hello"})
    assert send.status_code == 404
    ticket = await bob.post("/voice/ticket", json={"case_id": case["id"]})
    assert ticket.status_code == 404


async def test_citizen_cannot_use_admin_routes(client: httpx.AsyncClient) -> None:
    s = await register(client)
    for url in ("/admin/overview", "/admin/audit", "/admin/jobs", "/admin/agent-executions"):
        assert (await s.get(url)).status_code == 403


async def test_admin_can_see_operations(client: httpx.AsyncClient) -> None:
    s = await register(client)
    await make_admin(s.user["email"])
    overview = await s.get("/admin/overview")
    assert overview.status_code == 200
    health = await s.get("/admin/health?external=false")
    assert health.status_code == 200
    body = health.json()
    assert body["llm"]["status"] == "not_configured"
    assert body["legal_knowledge_base"]["status"] == "ok"


async def test_unauthenticated_requests_rejected(client: httpx.AsyncClient) -> None:
    client.cookies.clear()
    assert (await client.get("/api/v1/cases")).status_code == 401
    assert (await client.get("/api/v1/legal/search?q=consumer")).status_code == 401


async def test_tampered_token_rejected(client: httpx.AsyncClient) -> None:
    client.cookies.clear()
    resp = await client.get("/api/v1/cases", headers={"Authorization": "Bearer eyJhbGciOiJub25lIn0.e30."})
    assert resp.status_code == 401
