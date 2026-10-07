"""Allowlisted bundled assets, cached by file identity without caching user data."""
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).with_name('static')
ASSETS = {
    'style.css': 'text/css', 'xterm.css': 'text/css; charset=utf-8',
    'portal.js': 'text/javascript', 'host-terminal.js': 'text/javascript',
    'xterm.js': 'text/javascript', 'masthead.png': 'image/png',
    'session-background.png': 'image/png',
    'brand-arrow.svg': 'image/svg+xml', 'casualnetworks-arrow.svg': 'image/svg+xml',
    'provider-virtualbox.svg': 'image/svg+xml', 'provider-vmware.svg': 'image/svg+xml',
}

@lru_cache(maxsize=32)
def _read(path, modified, size, inode):
    body = path.read_bytes()
    return body, '"'+sha256(body).hexdigest()+'"'

def get(url):
    if not url.startswith('/static/'):
        return None
    name = url.removeprefix('/static/')
    if name not in ASSETS:
        return None
    path = ROOT / name
    stat = path.stat()
    body, etag = _read(path, stat.st_mtime_ns, stat.st_size, stat.st_ino)
    return body, ASSETS[name], etag
