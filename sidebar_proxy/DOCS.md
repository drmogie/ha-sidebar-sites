# Sidebar Proxy

Some websites refuse to load inside another page. This add-on fixes that.

## How it works

- You add a site and pick a port.
- The add-on serves that site on that port.
- It removes the headers that block frames.
- You use the new address in the Sidebar Sites integration.

## Options

- name: a label for you
- url: the real website, like http://192.168.1.50:3000
- port: a free port on this host, like 8101
- verify_ssl: turn off for self-signed certificates

## Example

- Site: http://192.168.1.50:3000
- Port: 8101
- Sidebar Sites URL: http://YOUR-HA-ADDRESS:8101

## Important limits

- The proxy address is plain HTTP.
- If you open HA over HTTPS, the browser blocks plain HTTP frames.
- Fix: put the proxy port behind Nginx Proxy Manager with its own subdomain and HTTPS.
- Use that HTTPS address in Sidebar Sites.
- The proxy has no login. Anyone on your network can open the port.
- Do not forward these ports to the internet without a login in front.
- Sites that check their own address may still refuse to load.
