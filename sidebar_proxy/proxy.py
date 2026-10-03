"""Sidebar Proxy: a small reverse proxy that lets any website load inside
a Home Assistant sidebar page (an iframe).

Each configured site gets its own port (8101, 8102, and so on, in order). The site is served from the root
of that port, so absolute paths on the site keep working. The proxy removes
the headers that stop a page from loading inside a frame.
"""
import asyncio
import html
import json
import logging
import ssl as ssl_lib
from urllib.parse import urlsplit

import aiohttp
from aiohttp import web

VERSION = "2026.10.02.02"
OPTIONS_FILE = "/data/options.json"
STATUS_PORT = 8099
FIRST_PORT = 8101
MAX_SITES = 10

LOG = logging.getLogger("sidebar_proxy")

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host",
}
# Headers we never copy from the website back to the browser.
DROP_RESPONSE = {
    "x-frame-options",
    "cross-origin-embedder-policy",
    "cross-origin-opener-policy",
    "content-length",  # recomputed by the streaming response
}
CSP_HEADERS = {"content-security-policy", "content-security-policy-report-only"}


def strip_frame_ancestors(value: str) -> str:
    """Remove the frame-ancestors rule from a CSP header value."""
    parts = [p.strip() for p in value.split(";")]
    kept = [p for p in parts if p and not p.lower().startswith("frame-ancestors")]
    return "; ".join(kept)


def fix_cookie(value: str) -> str:
    """Make a Set-Cookie value work on the plain proxy origin."""
    out = []
    for part in value.split(";"):
        low = part.strip().lower()
        if low.startswith("domain="):
            continue
        if low == "secure":
            continue
        if low == "samesite=none":
            out.append(" SameSite=Lax")
            continue
        out.append(part)
    return ";".join(out)


class Site:
    def __init__(self, conf: dict, index: int):
        self.name = conf["name"]
        self.port = FIRST_PORT + index
        self.target = conf["url"].rstrip("/")
        parts = urlsplit(self.target)
        self.origin = f"{parts.scheme}://{parts.netloc}"
        self.host = parts.netloc
        self.verify_ssl = conf.get("verify_ssl", True)

    def ssl_arg(self):
        if self.origin.startswith("https") and not self.verify_ssl:
            ctx = ssl_lib.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl_lib.CERT_NONE
            return ctx
        return None


def request_headers(request: web.Request, site: Site) -> dict:
    headers = {}
    for key, value in request.headers.items():
        low = key.lower()
        if low in HOP_BY_HOP:
            continue
        if low == "origin":
            value = site.origin
        elif low == "referer":
            value = site.origin + request.rel_url.path_qs
        headers[key] = value
    headers["Host"] = site.host
    return headers


def rewrite_location(value: str, site: Site) -> str:
    if value.startswith(site.origin):
        return value[len(site.origin):] or "/"
    return value


async def handle_websocket(request: web.Request, site: Site) -> web.StreamResponse:
    scheme = "wss" if site.origin.startswith("https") else "ws"
    url = f"{scheme}://{site.host}{request.rel_url.path_qs}"
    protocols = [
        p.strip()
        for p in request.headers.get("Sec-WebSocket-Protocol", "").split(",")
        if p.strip()
    ]
    session: aiohttp.ClientSession = request.app["session"]
    try:
        upstream = await session.ws_connect(
            url,
            headers={
                k: v for k, v in request_headers(request, site).items()
                if not k.lower().startswith("sec-websocket")
            },
            protocols=protocols,
            ssl=site.ssl_arg(),
        )
    except Exception as err:  # noqa: BLE001
        LOG.warning("[%s] websocket connect failed: %s", site.name, err)
        return web.Response(status=502, text="Upstream websocket failed")

    client = web.WebSocketResponse(protocols=protocols)
    await client.prepare(request)

    async def pump(src, dst):
        async for msg in src:
            if msg.type == aiohttp.WSMsgType.TEXT:
                await dst.send_str(msg.data)
            elif msg.type == aiohttp.WSMsgType.BINARY:
                await dst.send_bytes(msg.data)
            else:
                break
        await dst.close()

    await asyncio.gather(pump(client, upstream), pump(upstream, client),
                         return_exceptions=True)
    return client


async def handle(request: web.Request) -> web.StreamResponse:
    site: Site = request.app["site"]
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return await handle_websocket(request, site)

    session: aiohttp.ClientSession = request.app["session"]
    url = site.origin + request.rel_url.path_qs
    body = await request.read()
    try:
        upstream = await session.request(
            request.method,
            url,
            headers=request_headers(request, site),
            data=body if body else None,
            allow_redirects=False,
            ssl=site.ssl_arg(),
        )
    except Exception as err:  # noqa: BLE001
        LOG.warning("[%s] request failed: %s", site.name, err)
        return web.Response(
            status=502,
            text=f"Sidebar Proxy could not reach {site.target}: {err}",
        )

    response = web.StreamResponse(status=upstream.status, reason=upstream.reason)
    for key, value in upstream.headers.items():
        low = key.lower()
        if low in HOP_BY_HOP or low in DROP_RESPONSE or low == "set-cookie":
            continue
        if low in CSP_HEADERS:
            value = strip_frame_ancestors(value)
            if not value:
                continue
        elif low == "location":
            value = rewrite_location(value, site)
        response.headers.add(key, value)
    for cookie in upstream.headers.getall("Set-Cookie", []):
        response.headers.add("Set-Cookie", fix_cookie(cookie))

    if upstream.headers.get("Content-Length") and request.method != "HEAD":
        response.content_length = int(upstream.headers["Content-Length"])
    await response.prepare(request)
    async for chunk in upstream.content.iter_chunked(64 * 1024):
        await response.write(chunk)
    await response.write_eof()
    upstream.release()
    return response


async def start_site(site: Site) -> web.AppRunner:
    app = web.Application(client_max_size=0)
    app["site"] = site
    # auto_decompress off: bytes pass through exactly as the site sent them.
    app["session"] = aiohttp.ClientSession(
        auto_decompress=False, cookie_jar=aiohttp.DummyCookieJar()
    )
    app.router.add_route("*", "/{tail:.*}", handle)

    async def close_session(app_: web.Application):
        await app_["session"].close()

    app.on_cleanup.append(close_session)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", site.port).start()
    LOG.info("Proxying %s -> %s on port %s", site.name, site.target, site.port)
    return runner


async def start_status(sites: list[Site]) -> web.AppRunner:
    async def index(request: web.Request) -> web.Response:
        if sites:
            body = "".join(
                f"<li><b>{html.escape(s.name)}</b>: "
                f"<code>http://HOST:{s.port}</code> shows {html.escape(s.target)}</li>"
                for s in sites
            )
        else:
            body = "<li>No sites yet. Add some in the add-on Configuration tab.</li>"
        page = (
            "<!doctype html><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<style>body{font-family:sans-serif;margin:24px;line-height:1.5}"
            "@media(prefers-color-scheme:dark){body{background:#111;color:#eee}}"
            "</style>"
            f"<h2>Sidebar Proxy {VERSION}</h2>"
            "<p>Use these addresses as the site URL in the Sidebar Sites "
            "integration. Replace HOST with your Home Assistant address.</p>"
            f"<ul>{body}</ul>"
        )
        return web.Response(text=page, content_type="text/html")

    app = web.Application()
    app.router.add_get("/{tail:.*}", index)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", STATUS_PORT).start()
    return runner


def load_sites() -> list[Site]:
    try:
        with open(OPTIONS_FILE, encoding="utf-8") as fh:
            options = json.load(fh)
    except FileNotFoundError:
        options = {}
    items = options.get("sites", [])
    if len(items) > MAX_SITES:
        LOG.warning("Only the first %d sites are used", MAX_SITES)
    return [Site(item, i) for i, item in enumerate(items[:MAX_SITES])]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sites = load_sites()
    runners = [await start_site(site) for site in sites]
    runners.append(await start_status(sites))
    LOG.info("Sidebar Proxy %s ready with %d site(s)", VERSION, len(sites))
    try:
        await asyncio.Event().wait()
    finally:
        for runner in runners:
            await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
