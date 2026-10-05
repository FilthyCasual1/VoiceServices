"""Persistent, atomic per-source login budgets and safe authentication events."""
import ipaddress,logging,time
from . import security
_logger=logging.getLogger('serviceready.auth')
if not _logger.handlers:
    handler=logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s serviceready-auth %(message)s',datefmt='%Y-%m-%d %H:%M:%S'))
    _logger.addHandler(handler);_logger.setLevel(logging.WARNING);_logger.propagate=False

def initialize(app):
    with app.store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS login_failures(source TEXT PRIMARY KEY,start INTEGER NOT NULL,failures INTEGER NOT NULL,blocked_until INTEGER NOT NULL DEFAULT 0)')
        db.execute('CREATE TABLE IF NOT EXISTS login_limits(scope TEXT,source TEXT,start INTEGER NOT NULL,attempts INTEGER NOT NULL,PRIMARY KEY(scope,source))')
def source(env):
    try: return str(ipaddress.ip_address(env.get('REMOTE_ADDR','')))
    except ValueError: return 'unknown'
def reserve(app,env,scope):
    now=int(time.time());policy=security.settings(app);window=policy['window'];limit=policy['mfa_limit' if scope=='mfa' else 'login_limit'];ip=source(env)
    with app.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        blocked=db.execute('SELECT blocked_until FROM login_failures WHERE source=?',(ip,)).fetchone()
        if policy['automatic_blocks'] and blocked and blocked[0]>now: return blocked[0]-now
        db.execute('DELETE FROM login_limits WHERE start<=?',(now-window,))
        row=db.execute('SELECT start,attempts FROM login_limits WHERE scope=? AND source=?',(scope,ip)).fetchone()
        if row and row['attempts']>=limit: return max(1,row['start']+window-now)
        db.execute('INSERT INTO login_limits VALUES(?,?,?,1) ON CONFLICT(scope,source) DO UPDATE SET attempts=attempts+1',(scope,ip,now))
    return 0

def failed(env,scope,app=None):
    ip=source(env)
    if ip!='unknown': _logger.warning('%s_failed ip=%s',scope,ip)
    if app is not None:
        policy=security.settings(app);now=int(time.time())
        with app.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM login_failures WHERE start<=? AND blocked_until<=?',(now-policy['window'],now))
            row=db.execute('SELECT * FROM login_failures WHERE source=?',(ip,)).fetchone()
            count=(row['failures'] if row else 0)+1
            until=now+policy['block_seconds'] if policy['automatic_blocks'] and count>=policy['failure_limit'] else 0
            db.execute('INSERT OR REPLACE INTO login_failures VALUES(?,?,?,?)',(ip,row['start'] if row else now,count,until))
