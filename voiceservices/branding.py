"""Core branding and editable home blocks, independent of service addons."""
import html,json,re,secrets,struct
from pathlib import Path
from urllib.parse import urlsplit
E=lambda value:html.escape(str(value),quote=True)

def initialize(app):
    with app.store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS home_blocks(id INTEGER PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,url TEXT NOT NULL,position INTEGER NOT NULL,module TEXT NOT NULL,enabled INTEGER NOT NULL)')
        if not db.execute("SELECT 1 FROM module_metadata WHERE key='home-blocks-seeded'").fetchone():
            blocks=[('1. Get an account','Create your account to get started. Your administrator assigns access to the services available on your network.','/create-account',10,'',1),('2. Sign in','Sign in to configure your services and manage your account settings. Use My Account to change your password.','/login',20,'',1),('3. Set up your services','Storage: configure network shares and shared storage.\nVoice: set up phones and calling accounts.\nEmail: configure mailboxes and email clients.\nDomain services: set up your network identity and enroll devices.\nAvailable tools depend on the installed modules. Ask your administrator for setup details.','',30,'',1),('Downloads and setup','Download internal tools and applications for your machines.','/downloads',40,'downloads',1)]
            db.executemany('INSERT INTO home_blocks(title,body,url,position,module,enabled) VALUES(?,?,?,?,?,?)',blocks)
            db.execute("INSERT INTO module_metadata VALUES('home-blocks-seeded')")
def defaults(app):
    return dict({'title':'ServiceReady','subtitle':'ServiceReady INSAP'},**app.config.get('branding',{}))
def valid_url(value):
    if not value: return True
    if any(ord(c)<33 for c in value): return False
    if value.startswith('/') and not value.startswith('//') and '\\' not in value: return True
    p=urlsplit(value);return p.scheme in ('http','https') and bool(p.netloc) and not p.username and not p.password

def change(app,section,data):
    if section=='branding':
        title=data.get('title','').strip();subtitle=data.get('subtitle','').strip()
        if not 1<=len(title)<=80 or len(subtitle)>160: raise ValueError('Enter a title of 1–80 characters and a subtitle of at most 160 characters.')
        value=defaults(app);value.update(title=title,subtitle=subtitle)
        if data.get('reset_logo')=='yes': value.pop('logo',None)
        save(app,value);return 'Branding saved.'
    action=data.get('action','save')
    with app.store.connect() as db:
        if action=='delete': db.execute('DELETE FROM home_blocks WHERE id=?',(int(data.get('block','')),));return 'Block removed.'
        title=data.get('title','').strip();body=data.get('body','').strip();url=data.get('url','').strip();module=data.get('module','')
        from .modules import CATALOG
        if not 1<=len(title)<=120 or len(body)>5000 or not valid_url(url) or (module and module not in CATALOG): raise ValueError('Check block title, text, link and addon selection.')
        try: position=int(data.get('position','0'))
        except ValueError: raise ValueError('Enter a numeric block position.')
        values=(title,body,url,position,module,int(data.get('enabled')=='yes'))
        if data.get('block'):
            db.execute('UPDATE home_blocks SET title=?,body=?,url=?,position=?,module=?,enabled=? WHERE id=?',values+(int(data['block']),))
        else: db.execute('INSERT INTO home_blocks(title,body,url,position,module,enabled) VALUES(?,?,?,?,?,?)',values)
    return 'Home block saved.'
def save(app,value):
    with app.store.connect() as db: db.execute("INSERT OR REPLACE INTO portal_settings VALUES('branding',?)",(json.dumps(value),))
    app.config['branding']=value

def upload_logo(app,raw):
    if len(raw)>1024**2: raise ValueError('Logo must be at most 1 MiB.')
    if raw.startswith(b'\x89PNG\r\n\x1a\n') and len(raw)>=24 and raw[12:16]==b'IHDR':
        width,height=struct.unpack('>II',raw[16:24]);suffix='png'
        if not 0<width<=4096 or not 0<height<=4096: raise ValueError('Logo dimensions must be at most 4096 pixels.')
    elif raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9'): suffix='jpg'
    else: raise ValueError('Upload a PNG or JPEG logo.')
    root=Path(app.store.path).parent/'branding';root.mkdir(parents=True,exist_ok=True)
    name=secrets.token_hex(16)+'.'+suffix;(root/name).write_bytes(raw)
    value=defaults(app);old=value.get('logo');value['logo']=name;save(app,value)
    if old and re.fullmatch('[a-f0-9]{32}\\.(png|jpg)',old): (root/old).unlink(missing_ok=True)

def logo(app):
    name=defaults(app).get('logo','')
    if not re.fullmatch('[a-f0-9]{32}\\.(png|jpg)',name): return None
    path=Path(app.store.path).parent/'branding'/name
    if not path.is_file() or path.is_symlink(): return None
    return path.read_bytes(),'image/png' if name.endswith('.png') else 'image/jpeg'

def home(app):
    content='<p class="notice">Your starting point for setting up network services and managing your account.</p>'
    with app.store.connect() as db:
        for row in db.execute('SELECT * FROM home_blocks WHERE enabled=1 ORDER BY position,id'):
            if row['module'] and not app.modules.installed(row['module']): continue
            content+='<h2>'+E(row['title'])+'</h2><div class="panel"><p>'+E(row['body']).replace('\n','<br>')+'</p>'
            if row['url']: content+='<p><a href="'+E(row['url'])+'">'+E(row['title'])+'</a></p>'
            content+='</div>'
    return content

def render(app,section,user):
    csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
    if section=='branding':
        value=defaults(app)
        return '<div class="panel"><form method="post">'+csrf+'<label>Brand title</label><input name="title" maxlength="80" value="'+E(value['title'])+'" required><label>Subtitle</label><input name="subtitle" maxlength="160" value="'+E(value['subtitle'])+'"><label>Logo</label><select name="reset_logo"><option value="no">Keep current logo</option><option value="yes">Use default arrow</option></select><br><button>Save branding</button></form></div><div class="panel"><form action="/admin/branding/upload" method="post" enctype="multipart/form-data">'+csrf+'<label>Brand logo (PNG or JPEG, up to 1 MiB)</label><input type="file" name="file" accept="image/png,image/jpeg" required><br><button>Upload logo</button></form></div><p>The title appears in the masthead and browser tab. Your changes apply to all portal pages.</p>'
    from .modules import CATALOG
    def form(row):
        fields='<div class="panel"><form method="post">'+csrf+'<input type="hidden" name="block" value="'+E(row.get('id',''))+'">'
        for key,label,limit in [('title','Block title',120),('url','Link (optional)',500),('position','Position',10)]: fields+='<label>'+label+'</label><input name="'+key+'" maxlength="'+str(limit)+'" value="'+E(row.get(key,''))+'">'
        fields+='<label>Text</label><textarea name="body" rows="5" maxlength="5000">'+E(row.get('body',''))+'</textarea><label>Show when addon is installed</label><select name="module"><option value="">Always</option>'
        for key,(title,_) in CATALOG.items(): fields+='<option value="'+key+'"'+(' selected' if row.get('module')==key else '')+'>'+E(title)+'</option>'
        fields+='</select><label>Visibility</label><select name="enabled"><option value="yes">Visible</option><option value="no"'+(' selected' if row.get('enabled',1)==0 else '')+'>Hidden</option></select><br><button name="action" value="save">'+('Save block' if row.get('id') else 'Add block')+'</button>'
        if row.get('id'): fields+='<button name="action" value="delete">Remove block</button>'
        return fields+'</form></div>'
    content='<p>Edit blocks below. Lower position numbers appear first. Plain text and optional links are supported; blocks can depend on an installed addon.</p>'
    with app.store.connect() as db:
        for row in db.execute('SELECT * FROM home_blocks ORDER BY position,id'): content+='<h3>'+E(row['title'])+'</h3>'+form(dict(row))
    return content+'<h3>Add a block</h3>'+form({'position':50})
