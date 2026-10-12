import httpx


async def test_healthz_returns_ok(http_client: httpx.AsyncClient) -> None:
    resp = await http_client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
