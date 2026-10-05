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

## Update 2026-10-03 (versions .03.01 to .03.07)

- Integration: each sidebar site is its own config entry (service). Old single entry migrates by itself.
- Add-on ingress mode: pages are rewritten (HTML and CSS) and a JS shim patches fetch, XHR, WebSocket, EventSource.
  - Shim fixes: addresses with :443, relative addresses (no leading slash), URL( inside scripts, relative import().
- Add-on is now add-on only (.03.07): no ports, one sidebar item with a tab for each site (launcher page).
- Site ids = name with dashes (Dockge-250). Old numbers still work. Integration accepts proxy://Site-Name.
- Test flow: ha-pi4 first. Arc HA (arc-ha.d-a-d-s.dev) is the live test server. ha-blue untouched.
- Gotchas: Pi builds take about 5 minutes (tool calls time out, poll instead). Add-on may show error after update, press Start.
- Never write a file with open(p,"w") before reading it (this emptied config.yaml once, fixed in .03.04).

## 2026.10.03.08

- SHIM: forms with no action get one set to the proxy path (fixes OPNsense white page after login).
- verify_ssl is auto when unset: off for home hosts (is_home_host + HOME_NETS), on otherwise. home_networks option adds ranges.
- error_page() gives a styled 502. Session has sock_connect=10.

## 2026.10.04.05 to .09

- .05: use_login toggle with separate username and password boxes (replaces basic_login). Only on when use_login is true.
- .06: inline module scripts with static relative imports get a base tag (fixes blank page with dots after login).
- .07: http site that redirects to https on the same host switches scheme (rewrite_location).
- .08: pages with their own base tag (Cockpit) are followed. Shim fix() resolves against document.baseURI.
- .09: shim does not strip the ingress prefix inside named inner frames. Cockpit frames used to reload in a loop (double init, no data).
- Cockpit facts: frames named cockpit1:..., talk to the shell with postMessage. Page address inside frames must match what Cockpit sets.
- Debug tips: Chrome tool blocks output with cookie or query text, so strip those characters. Proxy log tail is about 100 lines.
- Version format reminder: YYYY.MM.DD.## with two digits.
