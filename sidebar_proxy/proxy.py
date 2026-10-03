"""Sidebar Proxy: a small reverse proxy that lets any website load inside
a Home Assistant sidebar page (an iframe).

Two ways to reach a site:

1. Port mode. Each site gets its own port (8101, 8102, and so on, in order).
   The site is served from the root of that port. Plain HTTP.
2. Ingress mode. Every site is also served through Home Assistant itself, at
   /s/<number>/ under the add-on's Ingress address. This is HTTPS when Home
   Assistant is HTTPS, and it is protected by the Home Assistant login. The
   proxy rewrites the page so its links, scripts and requests keep working
   under that path.

Both modes remove the headers that stop a page from loading inside a frame.
"""
import asyncio
import html
import json
import logging
import re
import ssl as ssl_lib
from urllib.parse import urlsplit

import aiohttp
from aiohttp import web

VERSION = "2026.10.03.02"
OPTIONS_FILE = "/data/options.json"
STATUS_PORT = 8099
FIRST_PORT = 8101
MAX_SITES = 10
MAX_REWRITE_BYTES = 8 * 1024 * 1024

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
    "content-length",  # recomputed
}
CSP_HEADERS = {"content-security-policy", "content-security-policy-report-only"}


def strip_frame_ancestors(value: str) -> str:
    """Remove the frame-ancestors rule from a CSP header value."""
    parts = [p.strip() for p in value.split(";")]
    kept = [p for p in parts if p and not p.lower().startswith("frame-ancestors")]
    return "; ".join(kept)


def fix_cookie(value: str, prefix: str | None = None) -> str:
    """Make a Set-Cookie value work on the proxy origin."""
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
        if prefix and low.startswith("path="):
            path = part.split("=", 1)[1].strip()
            if path.startswith("/"):
                out.append(f" Path={prefix}{path}")
                continue
        out.append(part)
    return ";".join(out)


class Site:
    def __init__(self, conf: dict, index: int):
        self.name = conf["name"]
        self.number = index + 1
        self.port = FIRST_PORT + index
        self.target = conf["url"].rstrip("/")
        parts = urlsplit(self.target)
        self.origin = f"{parts.scheme}://{parts.netloc}"
        self.host = parts.netloc
        self.base_path = parts.path.rstrip("/")
        self.verify_ssl = conf.get("verify_ssl", True)

    def ssl_arg(self):
        if self.origin.startswith("https") and not self.verify_ssl:
            ctx = ssl_lib.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl_lib.CERT_NONE
            return ctx
        return None


# ---------------------------------------------------------------------------
# Rewriting (ingress mode only)
# ---------------------------------------------------------------------------

SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")
ATTR_RE = re.compile(
    r"""(\s(?:src|href|action|poster|data-src|formaction)\s*=\s*)(["'])(.*?)\2""",
    re.I | re.S,
)
CSS_URL_RE = re.compile(r"""url\(\s*(["']?)(.*?)\1\s*\)""", re.I | re.S)
CSS_IMPORT_RE = re.compile(r"""(@import\s+)(["'])(.*?)\2""", re.I)
HEAD_RE = re.compile(r"<head[^>]*>", re.I)
CHARSET_RE = re.compile(r"charset=([\w\-]+)", re.I)


def fix_url(value: str, prefix: str, basedir: str, site: Site, relative: bool) -> str:
    """Point one URL at the proxy path.

    relative: when True, URLs without a leading slash are also rewritten (needed
    in HTML, because the shim changes the page address).
    """
    s = value.strip()
    if not s or s.startswith("#") or s.startswith("//"):
        return value
    if s.startswith(site.origin):
        s = s[len(site.origin):] or "/"
    elif SCHEME_RE.match(s):
        return value
    if s.startswith("/"):
        if s.startswith(prefix + "/") or s == prefix:
            return value
        return prefix + s
    if relative:
        return prefix + basedir + s
    return value


def rewrite_html(text: str, prefix: str, basedir: str, site: Site) -> str:
    def attr(match: re.Match) -> str:
        new = fix_url(match.group(3), prefix, basedir, site, True)
        return f"{match.group(1)}{match.group(2)}{new}{match.group(2)}"

    def css(match: re.Match) -> str:
        new = fix_url(match.group(2), prefix, basedir, site, False)
        return f"url({match.group(1)}{new}{match.group(1)})"

    text = ATTR_RE.sub(attr, text)
    text = CSS_URL_RE.sub(css, text)
    shim = f"<script>{SHIM.replace('__PREFIX__', json.dumps(prefix))}</script>"
    if HEAD_RE.search(text):
        return HEAD_RE.sub(lambda m: m.group(0) + shim, text, count=1)
    return shim + text


def rewrite_css(text: str, prefix: str, basedir: str, site: Site) -> str:
    def css(match: re.Match) -> str:
        new = fix_url(match.group(2), prefix, basedir, site, False)
        return f"url({match.group(1)}{new}{match.group(1)})"

    def imp(match: re.Match) -> str:
        new = fix_url(match.group(3), prefix, basedir, site, False)
        return f"{match.group(1)}{match.group(2)}{new}{match.group(2)}"

    return CSS_IMPORT_RE.sub(imp, CSS_URL_RE.sub(css, text))


# Runs first in every proxied page. Keeps scripts, requests and sockets that use
# root paths (like /api/users) working under the proxy path.
SHIM = r"""
(function () {
  var P = __PREFIX__;
  function dp(u) {
    return u.replace(/^((?:https?|wss?):\/\/[^\/:?#]+):(?:443|80)(?=[\/?#]|$)/i, "$1");
  }
  function fix(u) {
    if (typeof u !== "string") return u;
    u = dp(u);
    if (u.indexOf("//") === 0) return u;
    if (u.charAt(0) === "/") {
      return (u === P || u.indexOf(P + "/") === 0) ? u : P + u;
    }
    var o = location.origin;
    if (u.indexOf(o + "/") === 0) {
      var r = u.slice(o.length);
      return o + ((r === P || r.indexOf(P + "/") === 0) ? r : P + r);
    }
    return u;
  }
  try {
    var p = location.pathname;
    if (p.indexOf(P) === 0) {
      history.replaceState(history.state, "", (p.slice(P.length) || "/") + location.search + location.hash);
    }
  } catch (e) {}
  var f = window.fetch;
  if (f) {
    window.fetch = function (i, o) {
      try {
        if (typeof i === "string") i = fix(i);
        else if (i && i.url) i = new Request(fix(i.url), i);
      } catch (e) {}
      return f.call(this, i, o);
    };
  }
  var xo = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (m, u) {
    arguments[1] = fix(String(u));
    return xo.apply(this, arguments);
  };
  function wsfix(u) {
    u = dp(String(u));
    var o = location.origin.replace(/^http/, "ws");
    if (u.indexOf(o + "/") === 0) {
      var r = u.slice(o.length);
      return o + ((r === P || r.indexOf(P + "/") === 0) ? r : P + r);
    }
    if (u.charAt(0) === "/" && u.indexOf("//") !== 0) return o + fix(u);
    return u;
  }
  var W = window.WebSocket;
  window.WebSocket = function (u, pr) {
    u = wsfix(u);
    return pr === undefined ? new W(u) : new W(u, pr);
  };
  window.WebSocket.prototype = W.prototype;
  ["CONNECTING", "OPEN", "CLOSING", "CLOSED"].forEach(function (k) { window.WebSocket[k] = W[k]; });
  if (window.EventSource) {
    var E = window.EventSource;
    window.EventSource = function (u, c) { return new E(fix(String(u)), c); };
    window.EventSource.prototype = E.prototype;
  }
  var attrs = { src: 1, href: 1, action: 1, poster: 1 };
  var sa = Element.prototype.setAttribute;
  Element.prototype.setAttribute = function (n, v) {
    if (attrs[String(n).toLowerCase()] && typeof v === "string" && this.tagName !== "A") v = fix(v);
    return sa.call(this, n, v);
  };
  [[HTMLImageElement, "src"], [HTMLScriptElement, "src"], [HTMLLinkElement, "href"],
   [HTMLIFrameElement, "src"], [HTMLSourceElement, "src"], [HTMLMediaElement, "src"],
   [HTMLFormElement, "action"]].forEach(function (pair) {
    try {
      var d = Object.getOwnPropertyDescriptor(pair[0].prototype, pair[1]);
      if (!d || !d.set) return;
      Object.defineProperty(pair[0].prototype, pair[1], {
        get: d.get, configurable: true, enumerable: d.enumerable,
        set: function (v) { d.set.call(this, fix(String(v))); }
      });
    } catch (e) {}
  });
})();
"""


# ---------------------------------------------------------------------------
# Request and response helpers
# ---------------------------------------------------------------------------

def request_headers(request: web.Request, site: Site, ingress: bool) -> dict:
    headers = {}
    for key, value in request.headers.items():
        low = key.lower()
        if low in HOP_BY_HOP:
            continue
        if low == "origin":
            value = site.origin
        elif low == "referer":
            value = site.origin + "/"
        elif ingress and (low.startswith("x-ingress") or low.startswith("x-hass")
                          or low.startswith("x-forwarded")):
            continue
        elif ingress and low == "cookie":
            # Never pass the Home Assistant ingress login to the site.
            value = "; ".join(
                c for c in value.split("; ")
                if not c.strip().lower().startswith("ingress_session=")
            )
            if not value:
                continue
        elif ingress and low == "accept-encoding":
            continue
        headers[key] = value
    if ingress:
        headers["Accept-Encoding"] = "identity"
    headers["Host"] = site.host
    return headers


def rewrite_location(value: str, site: Site, prefix: str | None) -> str:
    if value.startswith(site.origin):
        value = value[len(site.origin):] or "/"
        return (prefix + value) if prefix else value
    if prefix and value.startswith("/") and not value.startswith("//"):
        return prefix + value
    return value


async def handle_websocket(
    request: web.Request, site: Site, rest: str, ingress: bool
) -> web.StreamResponse:
    scheme = "wss" if site.origin.startswith("https") else "ws"
    url = f"{scheme}://{site.host}{rest}"
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
                k: v for k, v in request_headers(request, site, ingress).items()
                if not k.lower().startswith("sec-websocket")
                and k.lower() != "accept-encoding"
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
        try:
            async for msg in src:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await dst.send_str(msg.data)
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    await dst.send_bytes(msg.data)
                else:
                    break
        except (ConnectionResetError, aiohttp.ClientError):
            pass
        await dst.close()

    await asyncio.gather(pump(client, upstream), pump(upstream, client),
                         return_exceptions=True)
    return client


async def proxy_request(
    request: web.Request, site: Site, rest: str, prefix: str | None
) -> web.StreamResponse:
    """Send one request to the site and return its answer.

    rest: path plus query, starting with a slash (relative to the site address).
    prefix: the proxy path in ingress mode, or None in port mode.
    """
    ingress = prefix is not None
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return await handle_websocket(request, site, site.base_path + rest, ingress)

    session: aiohttp.ClientSession = request.app["session"]
    url = site.origin + site.base_path + rest
    body = await request.read()
    try:
        upstream = await session.request(
            request.method,
            url,
            headers=request_headers(request, site, ingress),
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

    try:
        ctype = upstream.headers.get("Content-Type", "").split(";")[0].strip().lower()
        rewritable = (
            ingress
            and request.method != "HEAD"
            and upstream.status not in (204, 304)
            and ctype in ("text/html", "text/css")
            and not upstream.headers.get("Content-Encoding")
            and int(upstream.headers.get("Content-Length", "0") or 0) <= MAX_REWRITE_BYTES
        )

        out_headers = []
        for key, value in upstream.headers.items():
            low = key.lower()
            if low in HOP_BY_HOP or low in DROP_RESPONSE or low == "set-cookie":
                continue
            if low in CSP_HEADERS:
                if ingress:
                    continue  # a strict policy would block the page fix
                value = strip_frame_ancestors(value)
                if not value:
                    continue
            elif low == "location":
                value = rewrite_location(value, site, prefix)
            out_headers.append((key, value))
        cookies = [
            fix_cookie(c, prefix) for c in upstream.headers.getall("Set-Cookie", [])
        ]

        if rewritable:
            raw = await upstream.read()
            match = CHARSET_RE.search(upstream.headers.get("Content-Type", ""))
            encoding = match.group(1) if match else "utf-8"
            try:
                text = raw.decode(encoding, errors="replace")
            except LookupError:
                encoding = "utf-8"
                text = raw.decode(encoding, errors="replace")
            path_only = rest.split("?", 1)[0]
            basedir = path_only[: path_only.rfind("/") + 1] or "/"
            if ctype == "text/html":
                text = rewrite_html(text, prefix, basedir, site)
            else:
                text = rewrite_css(text, prefix, basedir, site)
            response = web.Response(status=upstream.status, body=text.encode(encoding))
            for key, value in out_headers:
                response.headers.add(key, value)
            for cookie in cookies:
                response.headers.add("Set-Cookie", cookie)
            return response

        response = web.StreamResponse(status=upstream.status, reason=upstream.reason)
        for key, value in out_headers:
            response.headers.add(key, value)
        for cookie in cookies:
            response.headers.add("Set-Cookie", cookie)
        if upstream.headers.get("Content-Length") and request.method != "HEAD":
            response.content_length = int(upstream.headers["Content-Length"])
        await response.prepare(request)
        try:
            async for chunk in upstream.content.iter_chunked(64 * 1024):
                await response.write(chunk)
            await response.write_eof()
        except (ConnectionResetError, aiohttp.ClientError):
            pass  # the browser left; nothing more to do
        return response
    finally:
        upstream.release()


# ---------------------------------------------------------------------------
# Servers
# ---------------------------------------------------------------------------

async def make_session() -> aiohttp.ClientSession:
    # auto_decompress off: bytes pass through exactly as the site sent them.
    return aiohttp.ClientSession(
        auto_decompress=False, cookie_jar=aiohttp.DummyCookieJar()
    )


async def start_site(site: Site) -> web.AppRunner:
    app = web.Application(client_max_size=0)
    app["site"] = site
    app["session"] = await make_session()

    async def handle(request: web.Request) -> web.StreamResponse:
        return await proxy_request(request, site, request.rel_url.raw_path_qs, None)

    async def close_session(app_: web.Application):
        await app_["session"].close()

    app.router.add_route("*", "/{tail:.*}", handle)
    app.on_cleanup.append(close_session)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", site.port).start()
    LOG.info("Port mode: %s -> %s on port %s", site.name, site.target, site.port)
    return runner


async def start_ingress(sites: list[Site]) -> web.AppRunner:
    by_number = {s.number: s for s in sites}

    async def index(request: web.Request) -> web.Response:
        if sites:
            body = "".join(
                f"<li><b>{html.escape(s.name)}</b> shows {html.escape(s.target)}<br>"
                f"Sidebar Sites address over HTTPS: <code>proxy://{s.number}</code><br>"
                f"Sidebar Sites address over plain HTTP: <code>http://HOST:{s.port}</code></li>"
                for s in sites
            )
        else:
            body = "<li>No sites yet. Add some in the add-on Configuration tab.</li>"
        page = (
            "<!doctype html><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<style>body{font-family:sans-serif;margin:24px;line-height:1.6}"
            "li{margin-bottom:14px}"
            "@media(prefers-color-scheme:dark){body{background:#111;color:#eee}}"
            "</style>"
            f"<h2>Sidebar Proxy {VERSION}</h2>"
            "<p>Use these addresses in the Sidebar Sites integration. "
            "Replace HOST with your Home Assistant address.</p>"
            f"<ul>{body}</ul>"
        )
        return web.Response(text=page, content_type="text/html")

    async def site_root(request: web.Request) -> web.StreamResponse:
        raise web.HTTPFound(request.headers.get("X-Ingress-Path", "")
                            + f"/s/{request.match_info['num']}/")

    async def handle(request: web.Request) -> web.StreamResponse:
        site = by_number.get(int(request.match_info["num"]))
        if site is None:
            return web.Response(status=404, text="No such site")
        number = request.match_info["num"]
        raw = request.rel_url.raw_path_qs
        rest = raw[len(f"/s/{number}"):] or "/"
        prefix = request.headers.get("X-Ingress-Path", "").rstrip("/") + f"/s/{number}"
        return await proxy_request(request, site, rest, prefix)

    app = web.Application(client_max_size=0)
    app["session"] = await make_session()

    async def close_session(app_: web.Application):
        await app_["session"].close()

    app.on_cleanup.append(close_session)
    app.router.add_get("/", index)
    app.router.add_route("*", r"/s/{num:\d+}", site_root)
    app.router.add_route("*", r"/s/{num:\d+}/{tail:.*}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", STATUS_PORT).start()
    LOG.info("Ingress mode ready on port %s", STATUS_PORT)
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
    runners.append(await start_ingress(sites))
    LOG.info("Sidebar Proxy %s ready with %d site(s)", VERSION, len(sites))
    try:
        await asyncio.Event().wait()
    finally:
        for runner in runners:
            await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
