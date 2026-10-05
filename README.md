# Sidebar Sites

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/github/v/release/drmogie/ha-sidebar-sites)](https://github.com/drmogie/ha-sidebar-sites/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Open any website inside Home Assistant, even sites on your home network.

This repo has two parts:

- **Sidebar Proxy** (add-on): all you need. It adds one sidebar item with a tab for each site.
- **Sidebar Sites** (integration): optional. It adds a separate sidebar item for each site.

## Install the add-on

1. Settings, Add-ons, Add-on Store, three dots, Repositories.
2. Add `https://github.com/drmogie/ha-sidebar-sites`.
3. Install Sidebar Proxy.
4. In Configuration, add your sites (name and address).
5. Start the add-on and turn on Show in sidebar.
6. Open Sidebar Sites in the sidebar. Click a tab.

No ports, no domain, no NPM host. It works over HTTPS and uses your Home Assistant login.
Each site gets an id: the name with dashes instead of spaces (Dockge 250 becomes Dockge-250).

See [sidebar_proxy/DOCS.md](sidebar_proxy/DOCS.md) for details.

## Optional: the integration (HACS)

Use it only if you want a separate sidebar item for each site.

1. HACS, then the three dots, Custom repositories.
2. Add `https://github.com/drmogie/ha-sidebar-sites` as type Integration.
3. Download Sidebar Sites. Restart Home Assistant.
4. Settings, Devices and services, Add integration, Sidebar Sites.
5. Use `proxy://Dockge-250` as the address to show a site from the add-on.

Every site is its own entry, with its own Configure and Delete.

## Limits

- Some sites (banks, Google sign-in) block frames on purpose and may still fail.
- This is early. Test on a test server first.

## Site login

- Some sites use a basic login box. Turn on use_login for that site, then fill in username and password.
- With use_login off, the add-on ignores both boxes.

## Tested sites

- Cockpit works, including its inner pages (fixed in 2026.10.04.09).
- Chrome and Chromium add-ons work over https.
- If a site sets its own base address or redirects http to https, the add-on follows it.

## Home networks and certificates

- Sites on a home network address skip the certificate check by default.
- Add more ranges with the home_networks option, for example `10.50.0.0/16`.
- Set verify_ssl on a site to force the check on or off.
- If a site cannot be reached, the tab shows a clear error page with a hint.
