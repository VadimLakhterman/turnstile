import logging
from unittest.mock import AsyncMock

import httpx
import pytest

from tests.conftest import CLIENT_ID, TX_HASH

GATEWAY_URL = f"/v1/gateway/{CLIENT_ID}"


async def test_unhandled_error_returns_generic_500_with_correlation_id(
    http_client: httpx.AsyncClient, mock_proxy: AsyncMock
) -> None:
    mock_proxy.forward.side_effect = RuntimeError("internal secret detail")
    resp = await http_client.post(GATEWAY_URL, headers={"X-Payment": TX_HASH, "X-Request-ID": "req-123"})
    assert resp.status_code == 500
    assert resp.json() == {"error": "Internal server error", "detail": None, "correlation_id": "req-123"}
    assert resp.headers["X-Request-ID"] == "req-123"
    assert "internal secret detail" not in resp.text


async def test_correlation_id_generated_when_absent(http_client: httpx.AsyncClient) -> None:
    resp = await http_client.get("/healthz")
    assert len(resp.headers["X-Request-ID"]) == 32


async def test_correlation_id_echoed_in_domain_error(http_client: httpx.AsyncClient) -> None:
    resp = await http_client.post(f"/v1/gateway/{'0' * 8}-0000-0000-0000-{'0' * 12}", headers={"X-Request-ID": "abc"})
    assert resp.status_code == 404
    assert resp.json()["correlation_id"] == "abc"
    assert resp.headers["X-Request-ID"] == "abc"


async def test_server_error_logged_once_with_traceback(
    http_client: httpx.AsyncClient, mock_proxy: AsyncMock, caplog: pytest.LogCaptureFixture
) -> None:
    from app.domain.errors import UpstreamUnavailableError

    try:
        raise ValueError("root cause")
    except ValueError as root:
        error = UpstreamUnavailableError("upstream failed")
        error.__cause__ = root
    mock_proxy.forward.side_effect = error

    with caplog.at_level(logging.ERROR, logger="app.core.errors"):
        await http_client.post(GATEWAY_URL, headers={"X-Payment": TX_HASH})

    records = [r for r in caplog.records if r.name == "app.core.errors"]
    assert len(records) == 1
    assert records[0].exc_info is not None
