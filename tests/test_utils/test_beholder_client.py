import typing

import pytest
from aiohttp import web

from alws.utils.beholder_client import BeholderClient

pytestmark = pytest.mark.anyio


@pytest.fixture
async def beholder_server() -> typing.AsyncIterator[dict]:
    """Local HTTP server that remembers the client port of every request."""
    state = {"client_ports": [], "headers": []}

    async def handler(request: web.Request) -> web.Response:
        state["client_ports"].append(
            request.transport.get_extra_info("peername")[1],
        )
        state["headers"].append(dict(request.headers))
        return web.json_response({"path": request.path})

    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    state["host"] = f"http://127.0.0.1:{port}"
    yield state
    await runner.cleanup()


async def test_requests_inside_context_reuse_connection(beholder_server):
    client = BeholderClient(beholder_server["host"], token="secret")
    async with client:
        first = await client.get("/api/v1/one/")
        await client.post("/api/v1/two/", {"source_rpms": []})
        await client.get("/api/v1/three/", headers={"X-Test": "1"})

    assert first == {"path": "/api/v1/one/"}
    assert len(set(beholder_server["client_ports"])) == 1
    assert all(
        headers["Authorization"] == "Bearer secret"
        for headers in beholder_server["headers"]
    )
    assert beholder_server["headers"][2]["X-Test"] == "1"
    assert "X-Test" not in beholder_server["headers"][0]
    assert client._session is None


async def test_requests_outside_context_open_own_sessions(beholder_server):
    client = BeholderClient(beholder_server["host"])
    await client.get("/api/v1/one/")
    await client.get("/api/v1/two/")

    assert len(set(beholder_server["client_ports"])) == 2
    assert client._session is None


async def test_nested_context_keeps_session_open(beholder_server):
    client = BeholderClient(beholder_server["host"])
    async with client:
        session = client._session
        async with client:
            await client.get("/api/v1/one/")
        assert client._session is session
        assert not session.closed
        await client.get("/api/v1/two/")
    assert session.closed
    assert client._session is None
    assert len(set(beholder_server["client_ports"])) == 1
