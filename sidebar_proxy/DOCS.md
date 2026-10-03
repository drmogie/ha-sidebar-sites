# Sidebar Proxy

Open any website inside Home Assistant. This works for sites on your home network too.
Some websites refuse to load inside another page. This add-on fixes that.
It also lets an HTTP site show inside an HTTPS Home Assistant.

## How to use it

1. Add your sites in the Configuration tab.
2. Start the add-on.
3. Turn on "Show in sidebar".
4. Open "Sidebar Sites" in the sidebar. Click a tab to open that site.

You do not need the Sidebar Sites integration. You do not need NPM hosts, domains, or ports.

## Site ids

- Every site gets an id. It is the name with dashes instead of spaces.
- "Dockge 250" becomes `Dockge-250`.
- Two sites with the same name get -2, -3, and so on.
- The old site number (1, 2, 3) still works as an id.
- If you use the Sidebar Sites integration, use `proxy://Dockge-250` as its address.

## Options

- name: the tab name. It also makes the id.
- url: the real website
- verify_ssl: turn off for self-signed certificates

## URL examples

- Another add-on: http://a0d7b954-nginxproxymanager:81
- A device on your network: http://192.168.1.50:3000

Add-on names like a0d7b954-nginxproxymanager work because this add-on shares the add-on network.

## Good to know

- The sidebar item is admin only.
- Uses your Home Assistant login. Works over HTTPS and over HTTP.
- The "New tab" button opens the site in its own tab. Keep Home Assistant open in another tab so your login stays valid.
- The page is rewritten so links and requests keep working. Most sites work. Some may not.
- The site runs on the same address as Home Assistant, like any add-on page. Only add sites you trust.
- Changed the sites? Restart the add-on.
