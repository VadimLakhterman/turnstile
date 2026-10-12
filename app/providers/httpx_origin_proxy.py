import httpx

from app.domain.errors import UpstreamUnavailableError
from app.domain.models import ProxyRequest, ProxyResponse

# httpx already decoded the body, so these no longer describe what we send back.
SKIP_RESPONSE_HEADERS = frozenset({"transfer-encoding", "content-encoding"})


class HttpxOriginProxy:
    """OriginProxy that POSTs to the client's origin over a shared httpx client."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def forward(self, url: str, request: ProxyRequest) -> ProxyResponse:
        try:
            response = await self._client.post(url=url, headers=request.headers, params=request.params, content=request.body)
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(f"Upstream request failed origin={url}") from exc

        return ProxyResponse(
            status_code=response.status_code,
            content=response.content,
            headers={k: v for k, v in response.headers.items() if k.lower() not in SKIP_RESPONSE_HEADERS},
        )
