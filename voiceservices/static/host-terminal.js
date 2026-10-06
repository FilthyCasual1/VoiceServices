/* Self-hosted xterm.js with session-bound, CSRF-protected PTY transport. */
(() => {
  let active, loading;
  async function library() {
    if (window.Terminal) return;
    if (!loading) loading = new Promise((resolve, reject) => {
      const style = document.createElement('link'); style.rel = 'stylesheet'; style.href = '/static/xterm.css'; document.head.append(style);
      const script = document.createElement('script'); script.src = '/static/xterm.js'; script.onload = resolve; script.onerror = reject; document.head.append(script);
    });
    return loading;
  }
  function encode(bytes) { let raw = ''; for (const b of bytes) raw += String.fromCharCode(b); return btoa(raw); }
  function stop() {
    if (!active) return;
    const previous = active; active = null; clearTimeout(previous.timer);
    if (previous.token) fetch('/admin/terminal/io', {method:'POST', credentials:'same-origin', keepalive:true, body:new URLSearchParams({csrf:previous.csrf, action:'close', token:previous.token})}).catch(() => {});
    previous.term?.dispose(); previous.observer?.disconnect();
  }
  async function request(state, action, fields = {}) {
    const response = await fetch('/admin/terminal/io', {method:'POST', credentials:'same-origin', body:new URLSearchParams({csrf:state.csrf, action, token:state.token || '', ...fields})});
    if (!response.headers.get('Content-Type')?.includes('application/json')) throw Error('Sign-in expired. Return to sign in.');
    const result = await response.json(); if (!response.ok) throw Error(result.error || 'Terminal request failed.'); return result;
  }
  function dimensions(state) {
    const width = state.screen.clientWidth; state.term.resize(Math.max(20, Math.min(240, Math.floor(width / 9))), 24);
    return {cols:String(state.term.cols), rows:String(state.term.rows)};
  }
  function boot() {
    const root = document.querySelector('#host-terminal'); if (!root || root.dataset.bound) return;
    root.dataset.bound = 'yes';
    const form = root.querySelector('[data-terminal-open]'), status = root.querySelector('[data-terminal-status]'), close = root.querySelector('[data-terminal-close]'), screen = root.querySelector('[data-terminal-screen]');
    close.addEventListener('click', () => { stop(); status.textContent = 'Disconnected'; form.hidden = false; close.disabled = true; });
    form.addEventListener('submit', async event => {
      event.preventDefault(); event.stopPropagation(); stop();
      const state = {csrf:root.dataset.csrf, status, screen, queue:Promise.resolve()}; active = state;
      let password = form.elements.password.value; form.elements.password.value = ''; form.querySelector('button').disabled = true;
      try {
        await library(); if (active !== state) return;
        const opened = await request(state, 'open', {password}); password = '';
        state.token = opened.token;
        if (active !== state) { fetch('/admin/terminal/io', {method:'POST',credentials:'same-origin',body:new URLSearchParams({csrf:state.csrf,action:'close',token:state.token})}).catch(()=>{}); return; }
        state.term = new window.Terminal({rows:24,cols:80,scrollback:1000,fontSize:14,allowProposedApi:false});
        state.term.open(screen); await request(state,'resize',dimensions(state)); state.term.focus(); form.hidden = true; close.disabled = false; status.textContent = 'Connected as your Linux account';
        state.term.onData(data => {
          const bytes = new TextEncoder().encode(data);
          for (let offset = 0; offset < bytes.length; offset += 2048) {
            const part = bytes.slice(offset, offset + 2048);
            state.queue = state.queue.then(async () => {
              if (active !== state) return;
              const result = await request(state,'write',{input:encode(part)});
              if (result.written !== part.length) throw Error('Input buffer full; some input was not sent.');
            }).catch(error => { status.textContent = error.message; stop(); form.hidden = false; close.disabled = true; });
          }
        });
        state.observer = new ResizeObserver(() => { if (active === state) state.queue = state.queue.then(() => request(state,'resize',dimensions(state))).catch(() => {}); }); state.observer.observe(screen);
        const poll = async () => {
          if (active !== state) return;
          try {
            const result = await request(state,'read'); if (active !== state) return;
            if (result.closed) throw Error('Shell closed.');
            if (result.data) state.term.write(Uint8Array.from(atob(result.data),c=>c.charCodeAt(0)));
            state.timer = setTimeout(poll,250);
          } catch(error) { status.textContent = error.message; stop(); form.hidden = false; close.disabled = true; }
        }; poll();
      } catch(error) { password = ''; status.textContent = error.message; stop(); form.hidden = false; close.disabled = true; }
      finally { form.querySelector('button').disabled = false; }
    });
  }
  window.ServiceReadyTerminal = {boot,stop}; window.addEventListener('pagehide',stop); boot();
})();
