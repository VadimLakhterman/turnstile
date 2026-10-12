import httpx
import pytest

from app.domain.errors import UpstreamUnavailableError
from app.domain.models import ProxyRequest
from app.providers.httpx_origin_proxy import HttpxOriginProxy

REQUEST = ProxyRequest(headers={"content-type": "application/json"}, params={"q": "1"}, body=b'{"a": 1}')


async def test_forward_sends_exact_request_and_strips_encoding_headers() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(201, content=b"done", headers={"x-origin": "yes", "transfer-encoding": "chunked"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await HttpxOriginProxy(client).forward("https://origin.test/api", REQUEST)

    assert len(captured) == 1
    sent = captured[0]
    assert sent.method == "POST"
    assert str(sent.url) == "https://origin.test/api?q=1"
    assert sent.headers["content-type"] == "application/json"
    assert sent.content == b'{"a": 1}'
    assert response.status_code == 201
    assert response.content == b"done"
    assert response.headers["x-origin"] == "yes"
    assert "transfer-encoding" not in {k.lower() for k in response.headers}


async def test_forward_wraps_transport_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(UpstreamUnavailableError) as exc_info:
            await HttpxOriginProxy(client).forward("https://origin.test/api", REQUEST)
    assert isinstance(exc_info.value.__cause__, httpx.ConnectError)
