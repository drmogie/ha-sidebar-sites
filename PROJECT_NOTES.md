# Project notes: ha-sidebar-sites

## 2026-10-02: first build

- Asked for: an add-on that forces a website to become a sidebar page.
- Built both: integration (sidebar pages) and add-on (proxy), one repo.
- Integration uses panel_custom with its own iframe web component.
- Add-on is a Python aiohttp proxy, one port per site, host network.
- Add-on strips X-Frame-Options and the frame-ancestors part of CSP.
- Proxy tested locally with a toy server: headers, redirect, cookie, websocket all passed.
- Names chosen without asking (no answer given): repo ha-sidebar-sites, domain sidebar_sites, add-on slug sidebar_proxy.
- Known limit: proxy is plain HTTP. HTTPS HA needs it behind NPM.
- Ingress was not used for the proxied site because ingress adds a path prefix that breaks most sites.

## 2026-10-02: second release (.02)

- Mogie's first test target: Nginx Proxy Manager admin at a0d7b954-nginxproxymanager:81 (add-on hostname).
- A host-network add-on cannot resolve add-on hostnames, so host_network was dropped.
- Ports are now fixed 8101 to 8110, assigned by site order. The port option was removed.

## 2026-10-02: tested on ha-pi4 (release .03)

- Repo created: drmogie/ha-sidebar-sites. Releases .01, .02, .03.
- Installed on ha-pi4 (HA 2026.9.4, LAN 172.16.90.75). Integration through HACS, add-on through the store.
- Test: NPM admin (a0d7b954-nginxproxymanager:81) as site 1 on proxy port 8101. NPM login page loads in the sidebar.
- Bug found and fixed in .03: page was cut short because host height 100% did not resolve. Now flex column, 100vh.
- Lesson: after changing panel.js, HA must restart so the ?v= module URL changes, or the browser keeps the old file.
- The add-on build on a Pi 4 takes several minutes; the MCP call times out at 60s but the build continues.
- Not yet tested: HTTPS HA with proxy behind NPM, websockets on a real site, ha-blue (production, not touched).
