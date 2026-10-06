/* Read-only probes; submitted forms are never replayed. */
(() => {
  let checking = false;
  setInterval(async () => {
    if (checking) return;
    checking = true;
    try {
      const response = await fetch('/healthz', {credentials: 'same-origin', cache: 'no-store'});
      if (response.ok && response.headers.get('Content-Type')?.includes('application/json')) {
        const destination = ['/admin', '/admin/system-updates'].includes(location.pathname) ? location.pathname : '/';
        location.replace(destination);
      }
    } catch (_) { /* Keep the recovery page visible until the portal is reachable. */ }
    finally { checking = false; }
  }, 5000);
})();
