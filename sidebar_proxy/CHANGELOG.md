# Changelog

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
