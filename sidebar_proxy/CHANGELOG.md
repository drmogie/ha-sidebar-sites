# Changelog

## 2026.10.03.14

- Fix: the error page no longer calls an unreachable address a certificate problem.

## 2026.10.03.13

- Fix: image lists (srcset) that hold an inline picture no longer break. This brings back the CasaOS logo.

## 2026.10.03.12

- New site options: hidden, rewrite, timeout, username and password.

## 2026.10.03.11

- Fix: fonts and icons in styles that a script adds to the page (CasaOS icon font) now load.

## 2026.10.03.10

- Fix: images, logos and backgrounds that a page adds with a script (CasaOS, Dockhand, Technitium) now load.

## 2026.10.03.09

- Fix: pages that load code with an absolute import (like the OPNsense Lobby dashboard widgets) now load in proxy mode.

## 2026.10.03.08

- Fix: login pages whose form has no address (like OPNsense) no longer end on a white page.
- Home network sites skip the certificate check by default. Built in: 10.x, 172.16 to 172.31, 192.168.x, 169.254.x, 127.x, 100.64 to 100.127, and local names.
- New option home_networks: add more address ranges, for example 203.0.113.0/24.
- verify_ssl set to true or false on a site still wins.
- A clear error page now shows when a site cannot be reached, with a hint on what to fix.
- Unreachable sites fail after 10 seconds.

## 2026.10.03.07

- Add-on only: one sidebar item with a tab for each site. No integration needed.
- Sites use ids from their names, with dashes instead of spaces (Dockge-250). Old numbers (1, 2, 3) still work.
- The direct ports (8101 and up) are gone. Everything goes through Home Assistant.
- Integration: addresses can now be proxy://Site-Name as well as proxy://1.

## 2026.10.03.06

- Fix: pages that load code with a relative import (for example Dockhand) now load in proxy mode.

## 2026.10.03.05

- Fix: pages with script code like new URL(...) (for example Dockhand) no longer break in proxy mode. The proxy changed the letter case of URL( inside scripts.

## 2026.10.03.04

- Same as 2026.10.03.03 (relative address fix for Technitium DNS). The .03 release had a broken add-on file, so use this one.

## 2026.10.03.03

- Fix: sites that ask for addresses without a leading slash, like Technitium DNS ("api/status"), now work in proxy mode.
- Add-on only. The integration is unchanged (2026.10.03.01).

## 2026.10.03.02

- Fix: sites that write their socket address with a port, like Dockge (:443), now work in proxy mode.
- Add-on only. The integration is unchanged (2026.10.03.01).

## 2026.10.02.06

- New: show any site through Home Assistant itself. Use `proxy://1` (site number) as the address in Sidebar Sites.
- Works over HTTPS, needs no domain and no NPM host, and uses your Home Assistant login.
- The add-on rewrites the page so links, scripts, requests and websockets keep working.
- Fix: quiet log noise when the browser closes a page early.

## 2026.10.02.03

- Fix: the sidebar page now fills the full height (the page was cut short).

## 2026.10.02.02

- Ports are now automatic: 8101, 8102, and so on (up to 10 sites).
- The add-on can now reach other add-ons by name, like a0d7b954-nginxproxymanager:81.
- Removed the port option.

## 2026.10.02.01

- First version.
- One port per site. Removes frame-blocking headers.
- Fixes redirects and cookies. Supports websockets.
