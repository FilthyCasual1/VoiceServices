/* Progressive navigation: preserve the appliance masthead and refresh stats only. */
(() => {
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
      document.querySelector('main').replaceWith(main);
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
    if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || link.target || link.hasAttribute('download')) return;
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin || /^(\/files\/|\/pxe\/|\/phone\/|\/branding\/|\/static\/)/.test(url.pathname)) return;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return;
    event.preventDefault(); visit(url.href);
  });
  document.addEventListener('submit', event => {
    const form = event.target;
    if (event.defaultPrevented || form.target || new URL(form.action).origin !== location.origin) return;
    event.preventDefault();
    const data = new FormData(form);
    if (event.submitter?.name) data.append(event.submitter.name, event.submitter.value);
    if (form.method.toLowerCase() === 'get') { const url = new URL(form.action); url.search = new URLSearchParams(data); visit(url.href); return; }
    const body = form.enctype === 'multipart/form-data' ? data : new URLSearchParams(data);
    visit(form.action, {method: 'POST', body}, 'push', true);
  });
  window.addEventListener('popstate', () => visit(location.href, {}, 'replace'));
  setInterval(async () => {
    if (document.hidden || navigating || polling || location.pathname.replace(/\/$/, '') !== '/admin' || !document.querySelector('.overview-grid')) return;
    polling = true; const revision = generation;
    try {
      const response = await fetch('/admin/overview-stats', {credentials: 'same-origin', headers: {'Accept': 'application/json'}});
      if ((response.redirected && new URL(response.url).pathname === '/login') || response.status === 401 || response.status === 403) { visit('/login', {}, 'replace'); return; }
      if (!response.ok || !response.headers.get('Content-Type')?.includes('application/json')) return;
      const result = await response.json();
      if (revision !== generation || navigating || !document.querySelector('.overview-grid')) return;
      const fragment = new DOMParser().parseFromString(result.html, 'text/html');
      morph(document.querySelector('.overview-grid'), fragment.querySelector('.overview-grid'));
      const note = document.querySelector('.overview-note'); if (note) morph(note, fragment.querySelector('.overview-note'));
    } catch (_) { /* Leave the last measured values visible during connection loss. */ }
    finally { polling = false; }
  }, 5000);
})();
