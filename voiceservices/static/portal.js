/* Progressive navigation: preserve the appliance masthead and refresh stats only. */
(() => {
  let refreshEnabled = true;
  try { refreshEnabled = localStorage.getItem('overview-refresh') !== 'off'; } catch (_) {}
  function refreshControl() {
    const input = document.querySelector('[data-overview-refresh]');
    if (input) { input.checked = refreshEnabled; input.closest('label').hidden = false; }
  }
  refreshControl();
  document.addEventListener('change', event => {
    if (!event.target.matches('[data-overview-refresh]')) return;
    refreshEnabled = event.target.checked;
    try { localStorage.setItem('overview-refresh', refreshEnabled ? 'on' : 'off'); } catch (_) {}
  });
  let navigating = false, generation = 0, polling = false, redirectTimer;
  function morph(current, incoming) {
    if (current.nodeType !== incoming.nodeType || current.nodeName !== incoming.nodeName) {
      current.replaceWith(incoming.cloneNode(true)); return;
    }
    if (current.nodeType === Node.TEXT_NODE) { if (current.nodeValue !== incoming.nodeValue) current.nodeValue = incoming.nodeValue; return; }
    if (current.nodeType !== Node.ELEMENT_NODE) return;
    for (const attr of [...current.attributes]) if (!incoming.hasAttribute(attr.name)) current.removeAttribute(attr.name);
    for (const attr of incoming.attributes) if (current.getAttribute(attr.name) !== attr.value) current.setAttribute(attr.name, attr.value);
    const old = [...current.childNodes], next = [...incoming.childNodes];
    next.forEach((node, i) => old[i] ? morph(old[i], node) : current.appendChild(node.cloneNode(true)));
    old.slice(next.length).forEach(node => node.remove());
  }
  function notice(message) {
    const p = document.createElement('p'); p.className = 'notice error'; p.textContent = message;
    document.querySelector('main')?.prepend(p);
  }
  async function visit(url, options = {}, historyMode = 'push', keepScroll = false) {
    if (navigating) return;
    navigating = true; const revision = ++generation; clearTimeout(redirectTimer);
    try {
      const response = await fetch(url, {credentials: 'same-origin', ...options});
      if (!response.headers.get('Content-Type')?.includes('text/html')) { location.assign(url); return; }
      const parsed = new DOMParser().parseFromString(await response.text(), 'text/html');
      const main = parsed.querySelector('main');
      if (!main || !parsed.querySelector('header')) throw new Error('Invalid portal response');
      if (revision !== generation) return;
      // A new software release requires its matching script and styles.
      if (parsed.querySelector('script[src]')?.getAttribute('src') !== document.querySelector('script[src]')?.getAttribute('src')) { location.assign(response.url); return; }
      if (keepScroll) {
        const opened = [...document.querySelectorAll('main details[open]')].map(el => el.querySelector('summary')?.textContent);
        for (const el of main.querySelectorAll('details')) if (opened.includes(el.querySelector('summary')?.textContent)) el.open = true;
      }
      window.ServiceReadyTerminal?.stop();
      document.querySelector('main').replaceWith(main);
      window.ServiceReadyTerminal?.boot();
      refreshControl();
      morph(document.querySelector('header'), parsed.querySelector('header'));
      morph(document.querySelector('nav'), parsed.querySelector('nav'));
      morph(document.querySelector('footer'), parsed.querySelector('footer'));
      const freshStyle = parsed.querySelector('link[data-brand-style]'), oldStyle = document.querySelector('link[data-brand-style]');
      if (freshStyle && oldStyle) morph(oldStyle, freshStyle);
      document.title = parsed.title;
      const target = new URL(response.url); target.hash = new URL(url, location.href).hash;
      if (historyMode === 'push') history.pushState(null, '', target);
      else if (historyMode === 'replace') history.replaceState(null, '', target);
      if (!keepScroll) window.scrollTo(0, 0);
      if (target.hash) { const el = document.getElementById(target.hash.slice(1)); if (el?.tagName === 'DETAILS') el.open = true; el?.scrollIntoView(); }
      if (target.pathname === '/logged-out') redirectTimer = setTimeout(() => visit('/login', {}, 'replace'), 5000);
    } catch (_) {
      // Never automatically retry a submitted form: it may already have been processed.
      notice('The page could not be loaded. Check your connection and reload before trying again.');
    } finally { navigating = false; }
  }
  document.addEventListener('click', event => {
    const link = event.target.closest('a');
    if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || link.target || link.hasAttribute('download') || link.hasAttribute('data-full-navigation')) return;
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin || url.pathname === '/admin/terminal' || /^(\/files\/|\/pxe\/|\/phone\/|\/branding\/|\/static\/)/.test(url.pathname)) return;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return;
    event.preventDefault(); visit(url.href);
  });
  document.addEventListener('submit', event => {
    const form = event.target;
    if (event.defaultPrevented || form.target || new URL(form.action).origin !== location.origin) return;
    event.preventDefault();
    if (form.hasAttribute('data-terminal-open')) return;
    if (form.hasAttribute('data-start-update')) {
      const panel = form.closest('[data-update-state]');
      if (panel) { panel.dataset.updateState = 'starting'; panel.dataset.updateIdlePolls = '0'; }
    }
    const data = new FormData(form);
    if (event.submitter?.name) data.append(event.submitter.name, event.submitter.value);
    if (form.method.toLowerCase() === 'get') { const url = new URL(form.action); url.search = new URLSearchParams(data); visit(url.href); return; }
    const body = form.enctype === 'multipart/form-data' ? data : new URLSearchParams(data);
    visit(form.action, {method: 'POST', body}, 'push', true);
  });
  window.addEventListener('popstate', () => visit(location.href, {}, 'replace'));
  let updatePolling = false;
  setInterval(async () => {
    const panel = document.querySelector('[data-update-state="running"], [data-update-state="starting"]');
    if (!panel || navigating || updatePolling) return;
    updatePolling = true; const revision = generation;
    try {
      const response = await fetch('/admin/update-status', {credentials: 'same-origin', headers: {'Accept': 'application/json'}});
      if ((response.redirected && new URL(response.url).pathname === '/login') || response.status === 401 || response.status === 403) { visit('/login', {}, 'replace'); return; }
      if (!response.ok || !response.headers.get('Content-Type')?.includes('application/json')) throw new Error('Update provider reconnecting');
      const result = await response.json();
      if (revision !== generation || navigating || !panel.isConnected) return;
      const state = result.status, message = panel.querySelector('[data-update-status]');
      if (!state || !message) return;
      if (state.state === 'idle' && panel.dataset.updateState === 'starting') {
        const attempts = Number(panel.dataset.updateIdlePolls || 0) + 1;
        panel.dataset.updateIdlePolls = String(attempts);
        message.textContent = attempts < 15 ? 'Starting update; waiting for the host worker…' : 'No update activity was reported. Check the host update service before trying again.';
        if (attempts >= 15) panel.dataset.updateState = 'idle';
      } else {
        panel.dataset.updateState = state.state;
        message.textContent = state.state + ': ' + (state.message || '');
      }
      message.classList.toggle('error', state.state === 'failed');
      for (const button of panel.querySelectorAll('[data-start-update] button')) button.disabled = ['running','starting'].includes(panel.dataset.updateState);
      if (['complete','failed'].includes(state.state) && result.version !== panel.dataset.updateVersion) visit(location.href, {}, 'replace', true);
    } catch (_) {
      if (revision === generation && panel.isConnected) {
        const message = panel.querySelector('[data-update-status]');
        if (message) message.textContent = 'Waiting for the portal or host update service to reconnect. Progress will resume automatically…';
      }
    } finally { updatePolling = false; }
  }, 2000);
  setInterval(async () => {
    if (!refreshEnabled || document.hidden || navigating || polling || location.pathname.replace(/\/$/, '') !== '/admin' || !document.querySelector('.overview-grid')) return;
    polling = true; const revision = generation;
    try {
      const response = await fetch('/admin/overview-stats', {credentials: 'same-origin', headers: {'Accept': 'application/json'}});
      if ((response.redirected && new URL(response.url).pathname === '/login') || response.status === 401 || response.status === 403) { visit('/login', {}, 'replace'); return; }
      if (!response.ok || !response.headers.get('Content-Type')?.includes('application/json')) return;
      const result = await response.json();
      if (!refreshEnabled || revision !== generation || navigating || !document.querySelector('.overview-grid')) return;
      const fragment = new DOMParser().parseFromString(result.html, 'text/html');
      morph(document.querySelector('.overview-grid'), fragment.querySelector('.overview-grid'));
      const note = document.querySelector('.overview-note'); if (note) morph(note, fragment.querySelector('.overview-note'));
    } catch (_) { /* Leave the last measured values visible during connection loss. */ }
    finally { polling = false; }
  }, 5000);
})();
