/* Sidebar Sites panel. Shows one website in an iframe. Version 2026.10.02.02 */
const SIDEBAR_SITES_VERSION = "2026.10.02.02";

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

  _render() {
    const { url, name } = this._config();
    const mixed =
      location.protocol === "https:" && /^http:/i.test(url);
    const esc = (t) =>
      String(t).replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
      }[c]));

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; height: 100%; background: var(--primary-background-color); }
        .bar { display: flex; align-items: center; gap: 4px; height: 56px; padding: 0 8px;
          box-sizing: border-box; background: var(--app-header-background-color, var(--primary-color));
          color: var(--app-header-text-color, #fff); }
        .title { flex: 1; font-size: 20px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        button, a.btn { background: none; border: 0; color: inherit; cursor: pointer; width: 40px; height: 40px;
          display: inline-flex; align-items: center; justify-content: center; border-radius: 50%; }
        button:hover, a.btn:hover { background: rgba(255,255,255,0.15); }
        svg { width: 24px; height: 24px; fill: currentColor; }
        iframe { border: 0; width: 100%; height: calc(100% - 56px); display: block; background: #fff; }
        .note { padding: 24px; color: var(--primary-text-color); max-width: 640px; line-height: 1.5; }
        .note a { color: var(--primary-color); }
      </style>
      <div class="bar">
        <button id="menu" title="Menu" style="${this._narrow ? "" : "display:none"}">
          <svg viewBox="0 0 24 24"><path d="${MENU_ICON}"/></svg>
        </button>
        <div class="title">${esc(name)}</div>
        <a class="btn" href="${esc(url)}" target="_blank" rel="noopener" title="Open in a new tab">
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
          : `<iframe src="${esc(url)}" title="${esc(name)}"
              allow="fullscreen; clipboard-read; clipboard-write; camera; microphone; geolocation; autoplay"
              allowfullscreen></iframe>`
      }`;

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
