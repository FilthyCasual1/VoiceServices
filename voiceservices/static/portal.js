/* Progressive navigation: preserve the appliance masthead and refresh stats only. */
(() => {
  let refreshEnabled = true;
  try { refreshEnabled = localStorage.getItem('overview-refresh') !== 'off'; } catch (_) {}
  function refreshControl() {
    let pending; try { pending = sessionStorage.getItem('insap-update-wizard'); } catch (_) {}
    const ready = pending ? document.getElementById(pending) : null;
    if (ready && !ready.open && ready.matches('[data-update-ready], [data-update-running], [data-update-result]')) { ready.showModal(); if (ready.hasAttribute('data-update-result')) { try { sessionStorage.removeItem('insap-update-wizard'); } catch (_) {} } }
    const setup=document.querySelector('[data-firstboot-wizard]');
    if(setup) for(const field of setup.querySelectorAll('[data-firstboot-step]')) field.hidden=field.dataset.firstbootStep!=='0';
    const installResult=document.querySelector('[data-install-step="result"]'); if (installResult) installResult.closest('dialog').showModal();
    const addon = document.querySelector('[data-addon-active]'); if (addon && !addon.open) addon.showModal();
    const input = document.querySelector('[data-overview-refresh]');
    if (input) { input.checked = refreshEnabled; input.closest('label').hidden = false; }
  }
  refreshControl();
  document.documentElement.classList.add('tools-wizard-ready');
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
      if (options.updateReconnect && !response.ok) throw new Error('Portal reconnecting');
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
      return true;
    } catch (_) {
      // Never automatically retry a submitted form: it may already have been processed.
      if (!options.updateReconnect) notice('The page could not be loaded. Check your connection and reload before trying again.');
      return false;
    } finally { navigating = false; }
  }
  document.addEventListener('pointerdown', event => {
    const header = event.target.closest('.tools-wizard > header');
    if (!header || event.target.closest('button') || event.button !== 0) return;
    const dialog = header.closest('dialog'), rect = dialog.getBoundingClientRect();
    const offsetX = event.clientX - rect.left, offsetY = event.clientY - rect.top;
    dialog.style.margin = '0'; dialog.style.position = 'fixed';
    dialog.style.left = rect.left + 'px'; dialog.style.top = rect.top + 'px';
    header.setPointerCapture(event.pointerId); event.preventDefault();
    const move = next => {
      dialog.style.left = Math.max(0, Math.min(innerWidth - dialog.offsetWidth, next.clientX - offsetX)) + 'px';
      dialog.style.top = Math.max(0, Math.min(innerHeight - dialog.offsetHeight, next.clientY - offsetY)) + 'px';
    };
    const finish = () => { header.removeEventListener('pointermove',move); header.removeEventListener('pointerup',finish); header.removeEventListener('pointercancel',finish); };
    header.addEventListener('pointermove',move); header.addEventListener('pointerup',finish); header.addEventListener('pointercancel',finish);
  });
  document.addEventListener('cancel', event => {
    if (event.target.id?.startsWith('update-')) { try { sessionStorage.removeItem('insap-update-wizard'); } catch (_) {} }
    if (event.target.hasAttribute?.('data-addon-active')) visit('/admin', {}, 'replace', true);
  }, true);
  document.addEventListener('click', event => {
    const dialogOpen=event.target.closest('[data-dialog-open]'); if (dialogOpen) { document.getElementById(dialogOpen.dataset.dialogOpen)?.showModal(); return; }
    const setupNext=event.target.closest('[data-firstboot-next]');
    if(setupNext){
      event.preventDefault();const form=setupNext.closest('form'),step=setupNext.dataset.firstbootNext;
      const current=form.querySelector('[data-firstboot-step]:not([hidden])');
      if(Number(step)>Number(current.dataset.firstbootStep)){
        for(const field of current.querySelectorAll('input,select'))if(!field.reportValidity())return;
        if(step==='2' && form.elements.password.value!==form.elements.confirm_password.value){form.elements.confirm_password.setCustomValidity('Passwords do not match.');form.elements.confirm_password.reportValidity();form.elements.confirm_password.setCustomValidity('');return;}
      }
      for(const field of form.querySelectorAll('[data-firstboot-step]'))field.hidden=field.dataset.firstbootStep!==step;
      if(step==='2')form.querySelector('[data-firstboot-review]').textContent='Create local administrator '+form.elements.username.value+' for '+form.elements.title.value+', using '+form.elements.timezone.value+'. Setup will close after saving.';
      return;
    }
    const installNext=event.target.closest('[data-install-next]');
    if (installNext) {
      const dialog=installNext.closest('dialog'),step=installNext.dataset.installNext;
      if (step==='2') {
        const selected=[...dialog.querySelectorAll('[data-repository-addon]:checked')];
        if (!selected.length) { const error=dialog.querySelector('[data-install-selection-error]'); error.hidden=false; error.textContent='Select at least one addon before continuing.'; return; }
        dialog.querySelector('[data-install-selection-error]').hidden=true;
        dialog.querySelector('[data-install-review]').textContent=selected.map(item=>item.dataset.addonTitle+' — '+item.dataset.addonVersion).join('; ');
        const fields=dialog.querySelector('[data-install-modules]');fields.replaceChildren();
        for (const item of selected) { const input=document.createElement('input');input.type='hidden';input.name='install_module_'+item.dataset.repositoryAddon;input.value='yes';fields.append(input); }
      }
      for (const panel of dialog.querySelectorAll('[data-install-step]')) panel.hidden=panel.dataset.installStep!==step;
      return;
    }
    const addonStep = event.target.closest('[data-addon-next]');
    if (addonStep) { const dialog=addonStep.closest('dialog'); for (const step of dialog.querySelectorAll('[data-addon-step]')) step.hidden=step.dataset.addonStep!==addonStep.dataset.addonNext; return; }
    const onboard = event.target.closest('[data-onboard-next]');
    if (onboard) {
      const form = onboard.closest('[data-onboarding]'), step = Number(onboard.dataset.onboardNext);
      const current = onboard.closest('[data-onboard-step]');
      if (step > Number(current.dataset.onboardStep)) {
        for (const input of current.querySelectorAll('input,select')) if (!input.reportValidity()) return;
        if (Number(current.dataset.onboardStep) === 0 && form.elements.password.value !== form.elements.confirm_password.value) { form.elements.confirm_password.setCustomValidity('Passwords do not match.'); form.elements.confirm_password.reportValidity(); form.elements.confirm_password.setCustomValidity(''); return; }
      }
      form.dataset.onboardActive = 'yes';
      for (const section of form.querySelectorAll('[data-onboard-step]')) section.hidden = Number(section.dataset.onboardStep) !== step;
      for (const marker of form.querySelectorAll('[data-onboard-marker]')) { if (Number(marker.dataset.onboardMarker) === step) marker.setAttribute('aria-current','step'); else marker.removeAttribute('aria-current'); }
      form.querySelector('[data-onboard-review]').textContent = 'Username: '+form.elements.username.value+' · Name: '+(form.elements.display_name.value || form.elements.username.value)+' · Email: '+(form.elements.email.value || 'Not provided')+' · Time zone: '+form.elements.timezone.value;
      form.querySelector('[data-onboard-step="'+step+'"]').querySelector('input,select,button')?.focus();
      return;
    }
    const updateOpener = event.target.closest('[data-update-open]');
    if (updateOpener) { document.getElementById(updateOpener.dataset.updateOpen).showModal(); return; }
    const opener = event.target.closest('[data-tools-open]');
    if (opener) { opener.parentElement.querySelector('[aria-labelledby="tools-title"]').showModal(); return; }
    const closer = event.target.closest('[data-tools-close]');
    if (closer) { const dialog = closer.closest('dialog'); dialog.close(); if (dialog.hasAttribute('data-addon-active')) { visit('/admin', {}, 'replace', true); } if (dialog.id.startsWith('update-')) { try { sessionStorage.removeItem('insap-update-wizard'); } catch (_) {} } return; }
    const stepButton = event.target.closest('[data-tools-next]');
    if (stepButton) {
      const form = stepButton.closest('[data-tools-wizard]');
      const step = Number(stepButton.dataset.toolsNext);
      form.dataset.toolsActive = 'yes';
      for (const section of form.querySelectorAll('[data-tools-step]')) section.hidden = Number(section.dataset.toolsStep) !== step;
      const provider = form.elements.tools_provider;
      const method = form.elements.update;
      form.querySelector('[data-tools-cd-choice]').hidden = provider.value !== 'virtualbox';
      if (provider.value !== 'virtualbox') method.value = 'vmtools';
      const review = form.querySelector('[data-tools-review]');
      review.textContent = (provider.value === 'vmware' ? 'VMware' : 'VirtualBox') + ' — ' + (method.value === 'vmtools-cd' ? 'Install from detected CD' : 'Recommended installation / update') + '.';
      for (const marker of form.querySelectorAll('[data-tools-marker]')) { if (Number(marker.dataset.toolsMarker) === step) marker.setAttribute('aria-current', 'step'); else marker.removeAttribute('aria-current'); }
      form.querySelector('[data-tools-step="' + step + '"]').querySelector('input,button')?.focus();
      return;
    }

    const link = event.target.closest('a');
    if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || link.target || link.hasAttribute('download') || link.hasAttribute('data-full-navigation')) return;
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin || ['/admin/terminal', '/admin/host'].includes(url.pathname) || /^(\/files\/|\/pxe\/|\/phone\/|\/branding\/|\/static\/)/.test(url.pathname)) return;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return;
    event.preventDefault(); visit(url.href);
  });
  document.addEventListener('submit', event => {
    const form = event.target;
    if (event.defaultPrevented || form.target || new URL(form.action).origin !== location.origin) return;
    event.preventDefault();
    if (form.hasAttribute('data-terminal-open')) return;
    if (form.hasAttribute('data-start-update')) {
      const wizard = form.closest('dialog[id^="update-"]');
      if (wizard) { try { sessionStorage.setItem('insap-update-wizard', wizard.id); } catch (_) {} }
      const panel = form.closest('[data-update-state]');
      if (panel) { panel.dataset.updateState = 'starting'; panel.dataset.updateIdlePolls = '0'; }
    }
    if (form.hasAttribute('data-tools-wizard')) { form.querySelector('[data-tools-progress]').hidden = false; form.querySelector('[data-tools-step="2"]').hidden = true; }
    const data = new FormData(form);
    if (event.submitter?.name) data.append(event.submitter.name, event.submitter.value);
    if (form.method.toLowerCase() === 'get') { const url = new URL(form.action); url.search = new URLSearchParams(data); visit(url.href); return; }
    const body = form.enctype === 'multipart/form-data' ? data : new URLSearchParams(data);
    if (form.hasAttribute('data-start-update') || form.hasAttribute('data-addon-install')) {
      for (const button of form.querySelectorAll('button:not([type="button"])')) button.disabled = true;
      const dialog = form.closest('dialog');
      if (dialog) { const progress = document.createElement('p'); progress.className='notice'; progress.setAttribute('role','status'); progress.textContent=form.hasAttribute('data-addon-install')?'Installing selected addons… Results will appear when installation finishes.':'Starting…'; form.append(progress); }
    }
    visit(form.action, {method: 'POST', body, updateReconnect:form.hasAttribute('data-start-update')}, 'push', true);
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
      if (panel.dataset.updateState === 'starting' && (state.state === 'idle' || (['complete','failed'].includes(state.state) && [state.kind,state.state,state.at || ''].join(':') === panel.dataset.toolsResult))) {
        const attempts = Number(panel.dataset.updateIdlePolls || 0) + 1;
        panel.dataset.updateIdlePolls = String(attempts);
        message.textContent = attempts < 15 ? 'Starting update; waiting for the host worker…' : 'No update activity was reported. Check the host update service before trying again.';
        if (attempts >= 15) {
          panel.dataset.updateState = 'idle';
          sessionStorage.removeItem('serviceready-pending-update');
          for (const button of panel.querySelectorAll('[data-start-update] button:not([type="button"])')) button.disabled = false;
        }
        return;
      } else {
        panel.dataset.updateState = state.state;
        message.textContent = state.state + ': ' + (state.message || '');
      }
      for (const other of panel.querySelectorAll('[data-update-status]')) { other.textContent = message.textContent; other.classList.toggle('error', state.state === 'failed'); }
      for (const button of panel.querySelectorAll('[data-start-update] button:not([type="button"])')) button.disabled = ['running','starting'].includes(panel.dataset.updateState);
      if (['complete','failed'].includes(state.state)) {
        panel.dataset.updateState = 'running';
        const loaded = await visit(location.href, {updateReconnect:true}, 'replace', true);
        if (!loaded && panel.isConnected) { panel.dataset.updateState = 'running'; message.textContent = 'Update finished; reconnecting to show the result…'; }
      }
    } catch (_) {
      if (revision === generation && panel.isConnected) {
        const message = panel.querySelector('[data-update-status]');
        if (message) message.textContent = 'Waiting for the portal or host update service to reconnect. Progress will resume automatically…';
      }
    } finally { updatePolling = false; }
  }, 2000);
  setInterval(async () => {
    if (document.querySelector('dialog[open]') || !refreshEnabled || document.hidden || navigating || polling || location.pathname.replace(/\/$/, '') !== '/admin' || !document.querySelector('.overview-grid')) return;
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
