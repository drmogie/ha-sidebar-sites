/* Sidebar Sites panel. Shows one website in an iframe. Version 2026.10.03.07 */
const SIDEBAR_SITES_VERSION = "2026.10.03.07";

const MENU_ICON =
  "M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z";
const OPEN_ICON =
  "M14,3V5H17.59L7.76,14.83L9.17,16.24L19,6.41V10H21V3M19,19H5V5H12V3H5C3.89,3 3,3.9 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V12H19V19Z";

class SidebarSitesPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._narrow = false;
    this._panel = null;
  }

  set hass(value) {
    this._hass = value;
  }

  set narrow(value) {
    this._narrow = !!value;
    const btn = this.shadowRoot.querySelector("#menu");
    if (btn) btn.style.display = this._narrow ? "" : "none";
  }

  set panel(value) {
    this._panel = value;
    this._render();
  }

  _config() {
    const cfg = (this._panel && this._panel.config) || {};
    return { url: cfg.site_url || "", name: cfg.site_name || "Site" };
  }

  _proxyId(url) {
    const m = /^proxy:\/\/([A-Za-z0-9._~-]{1,64})$/.exec(url || "");
    return m ? m[1] : "";
  }

  // Finds the Sidebar Proxy add-on and builds its Home Assistant (Ingress) address.
  async _loadProxy(id) {
    const note = (html) => {
      const el = this.shadowRoot.querySelector("#slot");
      if (el) el.innerHTML = `<div class="note">${html}</div>`;
    };
    try {
      for (let i = 0; i < 50 && !this._hass; i++) {
        await new Promise((r) => setTimeout(r, 100));
      }
      const hass = this._hass;
      if (!hass) throw new Error("Home Assistant is not ready.");
      const call = (endpoint, method, data) =>
        hass.callWS({ type: "supervisor/api", endpoint, method, ...(data ? { data } : {}) });
      const list = await call("/addons", "get");
      const addon = (list.addons || []).find((a) => /_sidebar_proxy$/.test(a.slug));
      if (!addon) throw new Error("The Sidebar Proxy add-on is not installed.");
      const info = await call(`/addons/${addon.slug}/info`, "get");
      if (info.state !== "started") throw new Error("The Sidebar Proxy add-on is not running. Start it first.");
      if (!info.ingress_url) throw new Error("The add-on has no Home Assistant address.");

      const setCookie = (session) => {
        document.cookie =
          `ingress_session=${session};path=/api/hassio_ingress/;SameSite=Strict` +
          (location.protocol === "https:" ? ";Secure" : "");
      };
      const created = await call("/ingress/session", "post");
      setCookie(created.session);
      clearInterval(this._renew);
      this._renew = setInterval(async () => {
        try {
          await call("/ingress/validate_session", "post", { session: created.session });
        } catch (e) {
          try {
            const fresh = await call("/ingress/session", "post");
            setCookie(fresh.session);
          } catch (e2) { /* try again next time */ }
        }
      }, 5 * 60 * 1000);

      const src = info.ingress_url.replace(/\/$/, "") + `/s/${encodeURIComponent(id)}/`;
      const frame = this.shadowRoot.querySelector("iframe");
      if (frame) frame.src = src;
      const open = this.shadowRoot.querySelector("#open");
      if (open) open.href = src;
    } catch (err) {
      const msg = String((err && (err.message || err.error || err.code)) || err)
        .replace(/[&<>"']/g, "");
      note(`<b>This page cannot load.</b><br>${msg}`);
    }
  }

  disconnectedCallback() {
    clearInterval(this._renew);
  }

  _render() {
    const { url, name } = this._config();
    const proxyId = this._proxyId(url);
    const mixed =
      !proxyId && location.protocol === "https:" && /^http:/i.test(url);
    const esc = (t) =>
      String(t).replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
      }[c]));

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: flex; flex-direction: column; height: 100vh; background: var(--primary-background-color); }
        .bar { display: flex; align-items: center; gap: 4px; height: 56px; padding: 0 8px;
          box-sizing: border-box; flex: none; background: var(--app-header-background-color, var(--primary-color));
          color: var(--app-header-text-color, #fff); }
        .title { flex: 1; font-size: 20px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        button, a.btn { background: none; border: 0; color: inherit; cursor: pointer; width: 40px; height: 40px;
          display: inline-flex; align-items: center; justify-content: center; border-radius: 50%; }
        button:hover, a.btn:hover { background: rgba(255,255,255,0.15); }
        svg { width: 24px; height: 24px; fill: currentColor; }
        iframe { border: 0; width: 100%; flex: 1; min-height: 0; display: block; background: #fff; }
        .note { padding: 24px; color: var(--primary-text-color); max-width: 640px; line-height: 1.5; }
        .note a { color: var(--primary-color); }
      </style>
      <div class="bar">
        <button id="menu" title="Menu" style="${this._narrow ? "" : "display:none"}">
          <svg viewBox="0 0 24 24"><path d="${MENU_ICON}"/></svg>
        </button>
        <div class="title">${esc(name)}</div>
        <a class="btn" id="open" href="${proxyId ? "#" : esc(url)}" target="_blank" rel="noopener" title="Open in a new tab">
          <svg viewBox="0 0 24 24"><path d="${OPEN_ICON}"/></svg>
        </a>
      </div>
      ${
        !url
          ? `<div class="note">No address is set for this page.</div>`
          : mixed
          ? `<div class="note"><b>This page cannot load here.</b><br>
              Home Assistant is open over HTTPS, but this site uses plain HTTP.
              The browser blocks that.<br><br>
              Fix: give the site an HTTPS address, for example with Nginx Proxy Manager.
              Or open it in a new tab: <a href="${esc(url)}" target="_blank" rel="noopener">${esc(url)}</a></div>`
          : `<div id="slot" style="display:contents"><iframe ${proxyId ? "" : `src="${esc(url)}"`} title="${esc(name)}"
              sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-modals allow-downloads allow-pointer-lock"
              allow="fullscreen; clipboard-read; clipboard-write; camera; microphone; geolocation; autoplay"
              allowfullscreen></iframe></div>`
      }`;
    if (proxyId) this._loadProxy(proxyId);

    const menu = this.shadowRoot.querySelector("#menu");
    if (menu) {
      menu.addEventListener("click", () =>
        this.dispatchEvent(
          new Event("hass-toggle-menu", { bubbles: true, composed: true })
        )
      );
    }
  }
}

if (!customElements.get("sidebar-sites-panel")) {
  customElements.define("sidebar-sites-panel", SidebarSitesPanel);
}
console.info(`%c SIDEBAR-SITES %c ${SIDEBAR_SITES_VERSION} `, "background:#03a9f4;color:#fff", "");
