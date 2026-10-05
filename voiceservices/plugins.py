"""Installable declarative phone plugins; packages cannot execute server code."""
import json
import re
from . import phone

class Plugins:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS plugins(id TEXT PRIMARY KEY, manifest TEXT NOT NULL, settings TEXT NOT NULL, enabled INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS plugin_metadata(key TEXT PRIMARY KEY)')
            if db.execute("SELECT 1 FROM plugin_metadata WHERE key='seeded'").fetchone(): return
            db.execute("INSERT INTO plugin_metadata VALUES('seeded')")
            db.execute('INSERT OR IGNORE INTO plugins VALUES(?,?,?,1)', ('calculator', json.dumps({'id':'calculator','name':'Calculator','version':'1.0','kind':'calculator','description':'Arithmetic on the telephone display.','fields':{}}), '{}'))

    def list(self):
        with self.store.connect() as db:
            return [dict(row, package=json.loads(row['manifest']), config=json.loads(row['settings'])) for row in db.execute('SELECT * FROM plugins ORDER BY id')]

    def install(self, raw):
        try: package = json.loads(raw)
        except (ValueError, TypeError): raise ValueError('Package must be valid JSON.')
        if not isinstance(package, dict): raise ValueError('Package must be an object.')
        for key in ('id','name','version','kind'):
            if not isinstance(package.get(key), str) or not 1 <= len(package[key]) <= 80: raise ValueError('Package requires id, name, version and kind.')
        if not re.fullmatch('[a-z][a-z0-9-]{0,39}', package['id']): raise ValueError('Invalid plugin ID.')
        if package['kind'] != 'text': raise ValueError('Uploaded plugins must use the text renderer.')
        fields = package.get('fields', {})
        if not isinstance(fields, dict) or len(fields)>12: raise ValueError('Maximum twelve configuration fields.')
        for key, label in fields.items():
            if not isinstance(key,str) or not re.fullmatch('[a-z][a-z0-9_]{0,30}',key) or not isinstance(label,str) or len(label)>80: raise ValueError('Invalid configuration field.')
        if not isinstance(package.get('text'),str) or len(package['text'])>4000: raise ValueError('Plugin requires phone text (maximum 4000 characters).')
        if len(str(package.get('description','')))>500: raise ValueError('Description too long.')
        placeholders = re.findall(r'\{([^{}]+)\}', package['text'])
        if any(key not in fields for key in placeholders): raise ValueError('Text placeholders must name configuration fields.')
        with self.store.connect() as db:
            if db.execute('SELECT 1 FROM plugins WHERE id=?',(package['id'],)).fetchone(): raise ValueError('Plugin ID already installed. Remove it before installing a replacement.')
            db.execute('INSERT INTO plugins VALUES(?,?,?,1)',(package['id'],json.dumps(package),'{}'))

    def change(self, plugin_id, data):
        item = next((p for p in self.list() if p['id']==plugin_id),None)
        if not item: raise ValueError('Plugin not found.')
        with self.store.connect() as db:
            if data.get('action')=='remove': db.execute('DELETE FROM plugins WHERE id=?',(plugin_id,))
            else:
                config = {key:data.get('config_'+key,'')[:500] for key in item['package'].get('fields',{})}
                db.execute('UPDATE plugins SET settings=?,enabled=? WHERE id=?',(json.dumps(config),int(data.get('enabled')=='yes'),plugin_id))

    def render(self, plugin_id, base, token):
        item = next((p for p in self.list() if p['id']==plugin_id and p['enabled']),None)
        if not item: return None
        package = item['package']
        if package['kind']=='calculator': return phone.calculator(base,token)
        message = re.sub(r'\{([^{}]+)\}',lambda match:item['config'].get(match[1],''),package['text'])
        return phone.text(package['name'],message)
