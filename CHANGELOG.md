# Changelog

## 2026.10.03.01

- Every sidebar site is now its own entry (its own service) in the integration list.
- Add a site with Add entry. Change it with Configure on that entry. Remove it with Delete on that entry.
- Sites from the old single entry move over by themselves. Their sidebar addresses stay the same.
- Add-on unchanged (still 2026.10.02.06).

## 2026.10.02.06

- New: show any site through Home Assistant itself. Use `proxy://1` (site number) as the address in Sidebar Sites.
- Works over HTTPS, needs no domain and no NPM host, and uses your Home Assistant login.
- The add-on rewrites the page so links, scripts, requests and websockets keep working.
- Fix: quiet log noise when the browser closes a page early.

## 2026.10.02.05

- Fix: sites that break out of the frame (and leave Home Assistant) are now kept inside the page.
- The page file now has a fingerprint, so changes show up without a restart or a cache clear.
- Add-on unchanged (still 2026.10.02.03).

## 2026.10.02.04

- Integration: you can now change a site (name, address, icon, admin only) from Configure, Change a site.
- The sidebar path stays the same when you rename a site.
- Add-on unchanged (still 2026.10.02.03).

## 2026.10.02.03

- Fix: the sidebar page now fills the full height (the page was cut short).

## 2026.10.02.02

- Add-on: ports are automatic (8101 and up). Can reach other add-ons by name.

## 2026.10.02.01

- First version.
- Integration: sidebar pages with a visual setup, add and remove sites.
- Add-on: Sidebar Proxy with one port per site.
