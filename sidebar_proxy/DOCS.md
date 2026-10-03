# Sidebar Proxy

Some websites refuse to load inside another page. This add-on fixes that.

## How it works

- You add a site in Configuration.
- The first site is served on port 8101. The second on 8102. And so on, up to 10.
- The add-on removes the headers that block frames.
- You use the new address in the Sidebar Sites integration.

## Options

- name: a label for you
- url: the real website
- verify_ssl: turn off for self-signed certificates

## URL examples

- Another add-on: http://a0d7b954-nginxproxymanager:81
- A device on your network: http://192.168.1.50:3000

Add-on names like a0d7b954-nginxproxymanager work because this add-on shares the add-on network.

## Using it

- Site 1 uses port 8101.
- In Sidebar Sites, set the address to http://YOUR-HA-ADDRESS:8101
- Check the Network section of this add-on. The ports must be switched on.

## Important limits

- The proxy address is plain HTTP.
- If you open HA over HTTPS, the browser blocks plain HTTP frames.
- Fix: put the proxy port behind Nginx Proxy Manager with its own subdomain and HTTPS.
- Use that HTTPS address in Sidebar Sites.
- The proxy has no login. Anyone on your network can open the port.
- Do not forward these ports to the internet without a login in front.
- Sites that check their own address may still refuse to load.
