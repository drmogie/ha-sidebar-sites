# Sidebar Proxy

Some websites refuse to load inside another page. This add-on fixes that.
It also lets an HTTP site show inside an HTTPS Home Assistant.

## How it works

- You add a site in Configuration. That is all.
- The first site is number 1, the second is number 2, and so on, up to 10.
- The add-on removes the headers that block frames.

## Two ways to show a site

1. Through Home Assistant (best). In Sidebar Sites, use the address `proxy://1` for site 1.
   - Works over HTTPS and over HTTP.
   - Needs no domain, no certificate, and no NPM host.
   - Uses your Home Assistant login. Only admins can see it.
   - The add-on fixes the page so its links and requests keep working.
2. Direct port (plain HTTP only). Site 1 is on port 8101, site 2 on 8102.
   - Use `http://YOUR-HA-ADDRESS:8101` in Sidebar Sites.
   - Check the Network section of this add-on. The ports must be switched on.
   - Blocked if you open Home Assistant over HTTPS.

## Options

- name: a label for you
- url: the real website
- verify_ssl: turn off for self-signed certificates

## URL examples

- Another add-on: http://a0d7b954-nginxproxymanager:81
- A device on your network: http://192.168.1.50:3000

Add-on names like a0d7b954-nginxproxymanager work because this add-on shares the add-on network.

## Limits

- Through Home Assistant, the page is rewritten. Most sites work. Some may not.
  Sites that build their own links in unusual ways can break.
- If a site does not work through Home Assistant, try the direct port.
- The site runs on the same address as Home Assistant, like any add-on page. Only add sites you trust.
- The direct ports have no login. Anyone on your network can open them.
- Do not forward the direct ports to the internet.
