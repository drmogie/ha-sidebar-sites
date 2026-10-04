"""Sidebar Proxy: a small reverse proxy that lets any website load inside
Home Assistant.

Every site is served through Home Assistant itself (Ingress), at
/s/<id>/ under the add-on's Ingress address. The id is the site name with
dashes instead of spaces (for example Dockge-250). This is HTTPS when Home
Assistant is HTTPS, and it is protected by the Home Assistant login. The proxy
removes the headers that stop a page from loading inside a frame, and rewrites
the page so its links, scripts and requests keep working under that path.

The add-on's own sidebar item shows a launcher page with one tab per site.
The older site number (/s/1/) still works as an id.
"""
import asyncio
import base64
import html
import ipaddress
import json
import logging
import re
import ssl as ssl_lib
from urllib.parse import urlsplit

import aiohttp
from aiohttp import web

VERSION = "2026.10.04.05"
OPTIONS_FILE = "/data/options.json"
STATUS_PORT = 8099
MAX_SITES = 50
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


# Addresses on a home network. HTTPS sites there almost always use a certificate
# the proxy cannot check (self-signed, or made for a name instead of the IP).
DEFAULT_HOME_NETS = [
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16",
    "127.0.0.0/8", "100.64.0.0/10", "fc00::/7", "fe80::/10", "::1/128",
]
LOCAL_SUFFIXES = (".local", ".lan", ".home", ".home.arpa", ".internal")
HOME_NETS: list = []


def parse_networks(items) -> list:
    nets = []
    for raw in items:
        raw = str(raw).strip()
        if not raw:
            continue
        try:
            nets.append(ipaddress.ip_network(raw, strict=False))
        except ValueError:
            LOG.warning("Ignoring home network %r: not an address range", raw)
    return nets


def is_home_host(host: str) -> bool:
    host = (host or "").strip("[]").lower()
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # a plain name like "router", or a local-style name like nas.local
        return "." not in host or host.endswith(LOCAL_SUFFIXES)
    return any(ip in net for net in HOME_NETS if net.version == ip.version)


def error_page(site, err) -> web.Response:
    """A readable page for when the proxy cannot reach a site."""
    text = str(err)
    low = text.lower()
    if "certificate" in low or "sslcertverification" in low or "ssl handshake" in low:
        why = "The site's security certificate was not trusted."
        todo = ("Set verify_ssl to false for this site in the add-on settings, "
                "or add its address range to home_networks. Then restart the add-on.")
    elif "refused" in low or "connect call failed" in low or "unreachable" in low:
        why = "Nothing answered at that address."
        todo = "Check that the site is running, and that the address and port are right."
    elif isinstance(err, asyncio.TimeoutError) or "timed out" in low or "timeout" in low:
        why = "The site did not answer in time."
        todo = "Check the address, that the device is on, and that nothing blocks Home Assistant."
    elif ("name or service" in low or "getaddrinfo" in low or "name resolution" in low
          or "nodename" in low):
        why = "The site's name could not be found."
        todo = "Check the spelling, or use the IP address instead."
    else:
        why = "The proxy could not connect to the site."
        todo = "Check the address in the add-on settings."
    page = (
        "<!doctype html><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<style>:root{color-scheme:light dark}"
        "body{font-family:Roboto,system-ui,sans-serif;margin:0;padding:28px;line-height:1.6}"
        "h2{margin:0 0 8px}code{background:rgba(127,127,127,.2);padding:1px 6px;border-radius:4px}"
        "pre{white-space:pre-wrap;background:rgba(127,127,127,.15);padding:10px;border-radius:6px;font-size:.85em}"
        "</style>"
        f"<h2>Cannot open {html.escape(site.name)}</h2>"
        f"<p><b>{html.escape(why)}</b></p>"
        f"<p>{html.escape(todo)}</p>"
        f"<p>Address: <code>{html.escape(site.target)}</code></p>"
        f"<pre>{html.escape(text)}</pre>"
    )
    # Not a 5xx: Cloudflare (and some other front doors) replace the body of an
    # origin 502 or 504 with their own "Bad gateway" page, hiding this one.
    return web.Response(status=424, text=page, content_type="text/html")


def make_id(name: str) -> str:
    """Site name -> id: dashes instead of spaces, only safe characters."""
    sid = re.sub(r"\s+", "-", name.strip())
    sid = re.sub(r"[^A-Za-z0-9._~-]", "-", sid)
    sid = re.sub(r"-{2,}", "-", sid).strip("-")
    return sid


class Site:
    def __init__(self, conf: dict, index: int):
        self.name = conf["name"]
        self.number = index + 1
        self.sid = make_id(self.name) or f"site-{self.number}"
        self.icon = conf.get("icon") or ""
        self.target = conf["url"].rstrip("/")
        parts = urlsplit(self.target)
        self.origin = f"{parts.scheme}://{parts.netloc}"
        self.host = parts.netloc
        self.base_path = parts.path.rstrip("/")
        self.hidden = bool(conf.get("hidden", False))
        self.rewrite = conf.get("rewrite", True) is not False
        timeout = conf.get("timeout")
        self.timeout = int(timeout) if timeout else None
        self.auth = None
        if conf.get("use_login") is True and conf.get("username"):
            raw = f"{conf['username']}:{conf.get('password') or ''}".encode()
            self.auth = "Basic " + base64.b64encode(raw).decode()
        explicit = conf.get("verify_ssl")
        if isinstance(explicit, bool):
            self.verify_ssl = explicit
            self.verify_note = "certificate check on" if explicit else "certificate check off"
        else:  # not set: check certificates, except for home network addresses
            home = is_home_host(parts.hostname or "")
            self.verify_ssl = not home
            self.verify_note = ("certificate check off (home network address)"
                                if home else "certificate check on")

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
SCRIPT_BLOCK_RE = re.compile(r"(<script\b.*?</script>)", re.I | re.S)
DYN_IMPORT_RE = re.compile(r"""\bimport\(\s*["']\.""")
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
        return f"{match.group(0)[:3]}({match.group(1)}{new}{match.group(1)})"

    text = ATTR_RE.sub(attr, text)
    # Leave script code alone (it can contain things like new URL(...)).
    parts = SCRIPT_BLOCK_RE.split(text)
    for i in range(0, len(parts), 2):
        parts[i] = CSS_URL_RE.sub(css, parts[i])
    text = "".join(parts)
    shim = f"<script>{SHIM.replace('__PREFIX__', json.dumps(prefix))}</script>"
    # Scripts that load code with a relative import("./x.js") resolve it against the
    # page base, which the shim moved. A base tag keeps those imports under the proxy.
    if DYN_IMPORT_RE.search(text):
        shim = f'<base href="{prefix}{basedir}">' + shim
    if HEAD_RE.search(text):
        return HEAD_RE.sub(lambda m: m.group(0) + shim, text, count=1)
    return shim + text


JS_IMPORT_RE = re.compile(r"""(?<![\w$.])import\(\s*(["'])/(?!/)""")
JS_TYPES = ("application/javascript", "text/javascript", "application/x-javascript")


def rewrite_js(text: str) -> str:
    """import("/x.js") ignores the page address, so send it through the shim."""
    return JS_IMPORT_RE.sub(lambda m: f"__sbImp({m.group(1)}/", text)


def rewrite_css(text: str, prefix: str, basedir: str, site: Site) -> str:
    def css(match: re.Match) -> str:
        new = fix_url(match.group(2), prefix, basedir, site, False)
        return f"{match.group(0)[:3]}({match.group(1)}{new}{match.group(1)})"

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
    if (u !== "" && u.charAt(0) !== "#" && !/^[a-z][a-z0-9+.\-]*:/i.test(u)) {
      try {
        var q = new URL(u, location.href);
        if (q.origin === o) {
          var h = q.pathname;
          return ((h === P || h.indexOf(P + "/") === 0) ? h : P + h) + q.search + q.hash;
        }
      } catch (e) {}
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
    var h = location.origin;
    if (u.indexOf(h + "/") === 0) {
      var q = u.slice(h.length);
      return o + ((q === P || q.indexOf(P + "/") === 0) ? q : P + q);
    }
    if (u.charAt(0) === "/" && u.indexOf("//") !== 0) return o + fix(u);
    return u;
  }
  // Workers start with a clean slate, so the fixes above would not reach a
  // WebSocket or fetch made inside one (the Selkies remote desktop does this).
  // Give each classic Worker a small preamble that applies the same fixes.
  function workerPre(P) {
    function fix(u) {
      if (u.charAt(0) === "/" && u.indexOf("//") !== 0) {
        return (u === P || u.indexOf(P + "/") === 0) ? u : P + u;
      }
      return u;
    }
    var h = location.origin, o = h.replace(/^http/, "ws");
    function wsfix(u) {
      u = String(u).replace(/^((?:https?|wss?):\/\/[^\/:?#]+):(?:443|80)(?=[\/?#]|$)/i, "$1");
      var b = u.indexOf(o + "/") === 0 ? o : (u.indexOf(h + "/") === 0 ? h : "");
      if (b) {
        var r = u.slice(b.length);
        return o + ((r === P || r.indexOf(P + "/") === 0) ? r : P + r);
      }
      if (u.charAt(0) === "/" && u.indexOf("//") !== 0) return o + fix(u);
      return u;
    }
    var W = self.WebSocket;
    if (W) {
      self.WebSocket = function (u, pr) {
        u = wsfix(u);
        return pr === undefined ? new W(u) : new W(u, pr);
      };
      self.WebSocket.prototype = W.prototype;
      ["CONNECTING", "OPEN", "CLOSING", "CLOSED"].forEach(function (k) { self.WebSocket[k] = W[k]; });
    }
    var F = self.fetch;
    if (F) {
      self.fetch = function (u, i) {
        if (typeof u === "string") {
          if (u.indexOf(h + "/") === 0) {
            var r = u.slice(h.length);
            u = h + ((r === P || r.indexOf(P + "/") === 0) ? r : P + r);
          } else u = fix(u);
        }
        return F.call(this, u, i);
      };
    }
  }
  var WK = window.Worker;
  if (WK) {
    window.Worker = function (u, opt) {
      try {
        var s = String(u);
        if (s.indexOf("blob:") === 0 && !(opt && opt.type === "module")) {
          var pre = "(" + workerPre.toString() + ")(" + JSON.stringify(P) + ");\n"
            + "importScripts(" + JSON.stringify(s) + ");";
          u = URL.createObjectURL(new Blob([pre], { type: "text/javascript" }));
        }
      } catch (e) {}
      return opt === undefined ? new WK(u) : new WK(u, opt);
    };
    window.Worker.prototype = WK.prototype;
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
  // A form with no action posts to the page address, which the shim moved.
  // Markup added by scripts (innerHTML, templates) skips the server rewrite.
  // Watch for it and fix src, href, srcset and inline css urls.
  var URLATTRS = ["src", "href", "poster", "data-src", "srcset", "style"];
  function fixCss(v) {
    return v.replace(/url\(\s*(["']?)(.*?)\1\s*\)/gi, function (m, q, u) {
      if (!u || u.charAt(0) === "#" || /^(data|blob):/i.test(u)) return m;
      return "url(" + q + fix(u) + q + ")";
    });
  }
  function fixAttrs(el) {
    if (!el || el.nodeType !== 1 || el.tagName === "SCRIPT") return;
    if (el.tagName === "STYLE") {
      var css = el.textContent;
      if (css && css.indexOf("url(") >= 0) {
        var nc = fixCss(css);
        if (nc !== css) el.textContent = nc;
      }
      return;
    }
    for (var i = 0; i < URLATTRS.length; i++) {
      var a = URLATTRS[i], v = el.getAttribute(a);
      if (!v) continue;
      var n;
      if (a === "style") { if (v.indexOf("url(") < 0) continue; n = fixCss(v); }
      else if (a === "srcset") {
        // entries are split on ", " so a data: url keeps its own comma
        n = v.split(/,\s+/).map(function (p) {
          var t = p.trim().split(/\s+/);
          if (!/^data:/i.test(t[0])) t[0] = fix(t[0]);
          return t.join(" ");
        }).join(", ");
      } else n = fix(v);
      if (n !== v) { try { el.setAttribute(a, n); } catch (e) {} }
    }
  }
  function fixTree(node) {
    if (!node || node.nodeType !== 1) return;
    fixAttrs(node);
    var all = node.querySelectorAll ? node.querySelectorAll("[src],[href],[poster],[data-src],[srcset],[style],style") : [];
    for (var i = 0; i < all.length; i++) fixAttrs(all[i]);
  }
  try {
    new MutationObserver(function (list) {
      for (var i = 0; i < list.length; i++) {
        var m = list[i];
        if (m.type === "attributes") fixAttrs(m.target);
        else {
          if (m.target.tagName === "STYLE") fixAttrs(m.target);
          for (var j = 0; j < m.addedNodes.length; j++) fixTree(m.addedNodes[j]);
        }
      }
    }).observe(document, { subtree: true, childList: true, attributes: true,
      attributeFilter: ["src", "poster", "srcset", "style", "data-src"] });
  } catch (e) {}
  window.__sbImp = function (u) { return import(fix(String(u))); };
  function fixForm(f) {
    try {
      if (f && f.tagName === "FORM" && !f.getAttribute("action")) {
        f.setAttribute("action", fix(location.pathname) + location.search);
      }
    } catch (e) {}
  }
  document.addEventListener("submit", function (e) { fixForm(e.target); }, true);
  var fsub = HTMLFormElement.prototype.submit;
  HTMLFormElement.prototype.submit = function () { fixForm(this); return fsub.apply(this, arguments); };
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
    if site.auth:
        headers["Authorization"] = site.auth
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
            **({"timeout": aiohttp.ClientTimeout(total=None, sock_connect=10,
                                                 sock_read=site.timeout)}
               if site.timeout else {}),
        )
    except Exception as err:  # noqa: BLE001
        LOG.warning("[%s] request failed: %s", site.name, err)
        return error_page(site, err)

    try:
        ctype = upstream.headers.get("Content-Type", "").split(";")[0].strip().lower()
        rewritable = (
            ingress
            and site.rewrite
            and request.method != "HEAD"
            and upstream.status not in (204, 304)
            and (ctype in ("text/html", "text/css") or ctype in JS_TYPES)
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
            elif ctype in JS_TYPES:
                text = rewrite_js(text)
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
        auto_decompress=False,
        cookie_jar=aiohttp.DummyCookieJar(),
        timeout=aiohttp.ClientTimeout(total=None, sock_connect=10),
    )


LAUNCHER = r"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sidebar Proxy</title>
<style>
:root{color-scheme:light dark;--bg:#fff;--fg:#1c1c1c;--bar:#f1f3f4;--line:#d0d4d8;--on:#03a9f4;--onfg:#fff}
@media(prefers-color-scheme:dark){:root{--bg:#111;--fg:#e8e8e8;--bar:#1e1e1e;--line:#333}}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{display:flex;flex-direction:column;background:var(--bg);color:var(--fg);font-family:Roboto,system-ui,sans-serif}
#bar{display:flex;gap:6px;align-items:center;padding:6px 8px;background:var(--bar);border-bottom:1px solid var(--line)}
#tabs{display:flex;gap:6px;flex-wrap:wrap;flex:1}
button{font:inherit;color:inherit;background:transparent;border:1px solid var(--line);border-radius:16px;padding:5px 14px;cursor:pointer}
button:hover{border-color:var(--on)}
button.on{background:var(--on);border-color:var(--on);color:var(--onfg)}
#tools button{border-radius:6px;padding:5px 10px}
#view{flex:1;border:0;width:100%;background:#fff}
#empty{padding:24px;line-height:1.6}
code{background:var(--bar);padding:1px 5px;border-radius:4px}
small{opacity:.7;padding:0 6px}
</style></head><body>
<div id="bar"><div id="tabs"></div>
<div id="tools"><button id="reload" title="Reload this site">Reload</button>
<button id="out" title="Open this site in a new tab, through Home Assistant">New tab</button>
<button id="go" title="Open the real address of this site, outside Home Assistant">Go to site</button></div>
<small>__VERSION__</small></div>
<div id="empty" hidden>No sites yet. Add some in the add-on Configuration tab, then restart the add-on.</div>
<iframe id="view" hidden
 sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-modals allow-downloads allow-pointer-lock"></iframe>
<script>
(function(){
  var BASE=__BASE__, SITES=__SITES__;
  var tabs=document.getElementById("tabs"), view=document.getElementById("view"), empty=document.getElementById("empty");
  var current=null;
  function url(s){return BASE+"/s/"+encodeURIComponent(s.id)+"/";}
  function pick(id){
    var s=SITES.filter(function(x){return x.id.toLowerCase()===String(id||"").toLowerCase();})[0]||SITES[0];
    if(!s)return;
    current=s;
    [].forEach.call(tabs.children,function(b){b.className=(b.dataset.id===s.id)?"on":"";});
    view.src=url(s);
    try{history.replaceState(null,"","#"+encodeURIComponent(s.id));}catch(e){}
    try{localStorage.setItem("sidebar-proxy-last",s.id);}catch(e){}
  }
  if(!SITES.length){empty.hidden=false;document.getElementById("tools").hidden=true;return;}
  view.hidden=false;
  SITES.forEach(function(s){
    var b=document.createElement("button");
    b.textContent=s.name;b.dataset.id=s.id;
    b.title="Address for Sidebar Sites: proxy://"+s.id;
    b.onclick=function(){pick(s.id);};
    tabs.appendChild(b);
  });
  document.getElementById("reload").onclick=function(){if(current)view.src=url(current);};
  document.getElementById("go").onclick=function(){if(current&&current.url)window.open(current.url,"_blank","noopener");};
  document.getElementById("out").onclick=function(){if(current)window.open(url(current),"_blank");};
  var start=decodeURIComponent((location.hash||"").slice(1));
  if(!start){try{start=localStorage.getItem("sidebar-proxy-last")||"";}catch(e){}}
  pick(start);
})();
</script></body></html>
"""


async def start_ingress(sites: list[Site]) -> web.AppRunner:
    by_id: dict[str, Site] = {}
    for s in sites:
        by_id[s.sid.lower()] = s
    for s in sites:  # the old site numbers keep working
        by_id.setdefault(str(s.number), s)

    async def index(request: web.Request) -> web.Response:
        base = request.headers.get("X-Ingress-Path", "").rstrip("/")
        data = [{"id": s.sid, "name": s.name, "url": s.target + "/"} for s in sites if not s.hidden]
        # "<" is escaped so a site name can never close the script tag.
        page = (
            LAUNCHER.replace("__BASE__", json.dumps(base))
            .replace("__SITES__", json.dumps(data).replace("<", "\\u003c"))
            .replace("__VERSION__", html.escape(VERSION))
        )
        return web.Response(text=page, content_type="text/html")

    async def site_root(request: web.Request) -> web.StreamResponse:
        raise web.HTTPFound(request.headers.get("X-Ingress-Path", "").rstrip("/")
                            + f"/s/{request.match_info['sid']}/")

    async def handle(request: web.Request) -> web.StreamResponse:
        sid = request.match_info["sid"]
        site = by_id.get(sid.lower())
        if site is None:
            return web.Response(status=404, text="No such site")
        raw = request.rel_url.raw_path_qs
        rest = raw[len(f"/s/{sid}"):] or "/"
        prefix = request.headers.get("X-Ingress-Path", "").rstrip("/") + f"/s/{sid}"
        return await proxy_request(request, site, rest, prefix)

    app = web.Application(client_max_size=0)
    app["session"] = await make_session()

    async def close_session(app_: web.Application):
        await app_["session"].close()

    app.on_cleanup.append(close_session)
    app.router.add_get("/", index)
    app.router.add_route("*", r"/s/{sid:[^/]+}", site_root)
    app.router.add_route("*", r"/s/{sid:[^/]+}/{tail:.*}", handle)
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
    extra = re.split(r"[,\s]+", str(options.get("home_networks") or ""))
    HOME_NETS[:] = parse_networks(DEFAULT_HOME_NETS) + parse_networks(extra)
    items = options.get("sites", [])
    if len(items) > MAX_SITES:
        LOG.warning("Only the first %d sites are used", MAX_SITES)
    sites = [Site(item, i) for i, item in enumerate(items[:MAX_SITES])]
    seen: set[str] = set()
    for s in sites:  # two sites with the same name get -2, -3 and so on
        base, n = s.sid, 1
        while s.sid.lower() in seen:
            n += 1
            s.sid = f"{base}-{n}"
        seen.add(s.sid.lower())
        extras = [x for x, on in (("hidden tab", s.hidden), ("no rewrite", not s.rewrite),
                                  (f"timeout {s.timeout}s", s.timeout),
                                  ("sign-in header", s.auth)) if on]
        LOG.info("Site %s -> %s  (address: proxy://%s, %s%s)",
                 s.name, s.target, s.sid, s.verify_note,
                 ", " + ", ".join(extras) if extras else "")
    return sites


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sites = load_sites()
    runner = await start_ingress(sites)
    LOG.info("Sidebar Proxy %s ready with %d site(s)", VERSION, len(sites))
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
