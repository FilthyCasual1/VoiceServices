"""Trusted optional platform modules; lifecycle state persists per deployment."""
ROUTES={'voice':{'exact':('/my-phone','/register-phone','/self-care','/preferences','/directory','/applications','/recordings'),'prefix':('/phone/',)},
        'server-management':{'exact':('/admin/settings','/network'),'prefix':()}}
CATALOG={
    'voice':('Voice Services','Phone setup, XML services, directory, phone plugins and voice-client downloads.'),
    'server-management':('Server Management','External application administration links and deployment configuration.'),
}
class Modules:
    def __init__(self,store):
        self.store=store
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS platform_modules(id TEXT PRIMARY KEY)')
            db.execute('CREATE TABLE IF NOT EXISTS module_metadata(key TEXT PRIMARY KEY)')
            if not db.execute("SELECT 1 FROM module_metadata WHERE key='seeded'").fetchone():
                db.executemany('INSERT OR IGNORE INTO platform_modules VALUES(?)',[(key,) for key in CATALOG])
                db.execute("INSERT INTO module_metadata VALUES('seeded')")
    def unavailable_for(self,path):
        for module,routes in ROUTES.items():
            if (path in routes['exact'] or any(path.startswith(prefix) for prefix in routes['prefix'])) and not self.installed(module): return module
        return None

    def installed(self,module):
        with self.store.connect() as db: return db.execute('SELECT 1 FROM platform_modules WHERE id=?',(module,)).fetchone() is not None
    def change(self,module,install):
        if module not in CATALOG: raise ValueError('Unknown platform module.')
        with self.store.connect() as db:
            if install: db.execute('INSERT OR IGNORE INTO platform_modules VALUES(?)',(module,))
            else: db.execute('DELETE FROM platform_modules WHERE id=?',(module,))
