"""Persistent, atomic per-source login budgets and safe authentication events."""
import ipaddress,logging,time
_logger=logging.getLogger('serviceready.auth')
if not _logger.handlers:
    handler=logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s serviceready-auth %(message)s',datefmt='%Y-%m-%d %H:%M:%S'))
    _logger.addHandler(handler);_logger.setLevel(logging.WARNING);_logger.propagate=False

def initialize(app):
    with app.store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS login_limits(scope TEXT,source TEXT,start INTEGER NOT NULL,attempts INTEGER NOT NULL,PRIMARY KEY(scope,source))')
def source(env):
    try: return str(ipaddress.ip_address(env.get('REMOTE_ADDR','')))
    except ValueError: return 'unknown'
def reserve(app,env,scope):
    now=int(time.time());window=300;limit=10;ip=source(env)
    with app.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM login_limits WHERE start<=?',(now-window,))
        row=db.execute('SELECT start,attempts FROM login_limits WHERE scope=? AND source=?',(scope,ip)).fetchone()
        if row and row['attempts']>=limit: return max(1,row['start']+window-now)
        db.execute('INSERT INTO login_limits VALUES(?,?,?,1) ON CONFLICT(scope,source) DO UPDATE SET attempts=attempts+1',(scope,ip,now))
    return 0

def failed(env,scope):
    ip=source(env)
    if ip!='unknown': _logger.warning('%s_failed ip=%s',scope,ip)
