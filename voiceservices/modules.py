"""Trusted optional platform modules; lifecycle state persists per deployment."""
ROUTES={'downloads':{'exact':('/downloads','/admin/downloads'),'prefix':('/files/downloads/',)},
        'pxe':{'exact':('/admin/pxe',),'prefix':('/pxe/',)},
        'voice':{'exact':('/my-phone','/register-phone','/self-care','/preferences','/directory','/applications','/recordings'),'prefix':('/phone/',)},
        'server-management':{'exact':('/admin/settings','/network'),'prefix':()}}
CATALOG={
    'downloads':('Downloads','Internal tools and applications: uploaded packages and repository links.'),
    'pxe':('PXE and Image Deployment','iPXE ISO boot menus and interactive Clonezilla image restoration.'),
    'voice':('Voice Services','Phone setup, XML services, directory, phone plugins and voice setup tools.'),
    'server-management':('Server Management','External application administration links and deployment configuration.'),
}
class Modules:
    def __init__(self,store,initial_modules=None):
        self.store=store
        initial_modules=list(initial_modules) if initial_modules is not None else ['voice','server-management','downloads']
        if any(key not in CATALOG for key in initial_modules): raise ValueError('Unknown initial module.')
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS platform_modules(id TEXT PRIMARY KEY)')
            db.execute('CREATE TABLE IF NOT EXISTS module_metadata(key TEXT PRIMARY KEY)')
            if not db.execute("SELECT 1 FROM module_metadata WHERE key='seeded'").fetchone():
                db.executemany('INSERT OR IGNORE INTO platform_modules VALUES(?)',[(key,) for key in initial_modules])
                db.execute("INSERT INTO module_metadata VALUES('seeded')")
                db.execute("INSERT INTO module_metadata VALUES('downloads-migrated')")
            if not db.execute("SELECT 1 FROM module_metadata WHERE key='downloads-migrated'").fetchone():
                db.execute("INSERT OR IGNORE INTO platform_modules VALUES('downloads')")
                db.execute("INSERT INTO module_metadata VALUES('downloads-migrated')")
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
