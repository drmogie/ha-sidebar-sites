# Sidebar Sites

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/github/v/release/drmogie/ha-sidebar-sites)](https://github.com/drmogie/ha-sidebar-sites/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Show any website as a page in the Home Assistant sidebar.

This repo has two parts:

- **Sidebar Sites** (integration): adds the sidebar pages.
- **Sidebar Proxy** (add-on): fixes sites that refuse to load in a frame.

## Install the integration (HACS)

1. HACS, then the three dots, then Custom repositories.
2. Add `https://github.com/drmogie/ha-sidebar-sites` as type Integration.
3. Download Sidebar Sites. Restart Home Assistant.
4. Settings, Devices and services, Add integration, Sidebar Sites.
5. Press Configure, then Add a site.

Each site needs a name, an address, and an icon.
Each site gets its own sidebar item.

## Install the add-on (only if a site will not load)

1. Settings, Add-ons, Add-on Store, three dots, Repositories.
2. Add `https://github.com/drmogie/ha-sidebar-sites`.
3. Install Sidebar Proxy.
4. In Configuration, add the site (name and address).
5. Start the add-on.
6. Site 1 is on port 8101, site 2 on 8102, and so on.
7. In Sidebar Sites, use `http://YOUR-HA-ADDRESS:8101` as the address.

See [sidebar_proxy/DOCS.md](sidebar_proxy/DOCS.md) for details.

## Limits

- HTTPS Home Assistant cannot frame plain HTTP sites. Put the proxy port behind HTTPS.
- The proxy port has no login. Keep it on your home network.
- Some sites (banks, Google sign-in) block frames on purpose and may still fail.
- This is early. Test on a test server first.
