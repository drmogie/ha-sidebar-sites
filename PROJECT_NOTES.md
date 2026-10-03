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
