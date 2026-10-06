import html
from urllib.parse import urlsplit,parse_qs,quote
from voiceservices.library import Library
E=lambda value:html.escape(str(value or ''),quote=True)

class DownloadLibrary(Library):
    def __init__(self,*args):
        super().__init__(*args)
        with self.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS downloads_catalog(id INTEGER PRIMARY KEY,title TEXT,version TEXT,platform TEXT,url TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS downloads_categories(id INTEGER PRIMARY KEY,name TEXT NOT NULL COLLATE NOCASE UNIQUE)')
            db.execute('CREATE TABLE IF NOT EXISTS downloads_details(kind TEXT NOT NULL,item TEXT NOT NULL,title TEXT,version TEXT,platform TEXT,description TEXT,category INTEGER,PRIMARY KEY(kind,item))')
    def categories(self):
        with self.store.connect() as db:return db.execute('SELECT * FROM downloads_categories ORDER BY name COLLATE NOCASE').fetchall()
    def category(self,value):
        if not value:return None
        try:value=int(value)
        except (TypeError,ValueError):raise ValueError('Choose an existing category.')
        if not any(row['id']==value for row in self.categories()):raise ValueError('Choose an existing category.')
        return value
    def save_category(self,data):
        name=data.get('name','').strip()
        if not name or len(name)>60:raise ValueError('Enter a category name of at most 60 characters.')
        with self.store.connect() as db:
            if db.execute('SELECT 1 FROM downloads_categories WHERE name=? AND id!=?',(name,int(data.get('category') or 0))).fetchone():raise ValueError('A category with that name already exists.')
            if data.get('category'):
                if db.execute('UPDATE downloads_categories SET name=? WHERE id=?',(name,self.category(data['category']))).rowcount!=1:raise ValueError('Category no longer exists.')
            else:db.execute('INSERT INTO downloads_categories(name) VALUES(?)',(name,))
    def remove_category(self,value):
        value=self.category(value)
        with self.store.connect() as db:
            db.execute('UPDATE downloads_details SET category=NULL WHERE category=?',(value,))
            db.execute('DELETE FROM downloads_categories WHERE id=?',(value,))
    def add_link(self,data):
        url=data.get('url','');parsed=urlsplit(url)
        if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or parsed.password or any(ord(c)<33 for c in url):raise ValueError('Enter a valid HTTP(S) download URL without credentials or whitespace.')
        title=data.get('title','').strip()
        if not title or len(title)>100:raise ValueError('Enter a title of at most 100 characters.')
        category=self.category(data.get('category',''))
        with self.store.connect() as db:
            item=db.execute('INSERT INTO downloads_catalog(title,version,platform,url) VALUES(?,?,?,?)',(title,data.get('version','')[:80],data.get('platform','')[:80],url)).lastrowid
            db.execute('INSERT INTO downloads_details VALUES(?,?,?,?,?,?,?)',('link',str(item),title,data.get('version','')[:80],data.get('platform','')[:80],data.get('description','')[:1000],category))
    def remove_link(self,value):
        with self.store.connect() as db:
            db.execute('DELETE FROM downloads_catalog WHERE id=?',(int(value),))
            db.execute("DELETE FROM downloads_details WHERE kind='link' AND item=?",(str(value),))
    def remove_file(self,data):
        name=data.get('item','')
        if data.get('confirm')!='yes':raise ValueError('Confirm deletion of the uploaded file.')
        if not any(row['name']==name for row in self.files()):raise ValueError('Download no longer exists.')
        self.require_volume()
        path=self.root/name
        if path.is_symlink() or path.parent!=self.root:raise ValueError('Invalid download file.')
        try:path.unlink()
        except FileNotFoundError:pass
        except OSError:raise ValueError('Unable to delete the file. Check the upload disk and try again.') from None
        with self.store.connect() as db:
            db.execute('DELETE FROM downloads_files WHERE name=?',(name,))
            db.execute("DELETE FROM downloads_details WHERE kind='file' AND item=?",(name,))
    @staticmethod
    def size(value):
        for unit in ('B','KB','MB','GB','TB'):
            if value<1024 or unit=='TB':return (str(int(value)) if unit=='B' else f'{value:.1f}')+' '+unit
            value/=1024
    def catalog(self):
        with self.store.connect() as db:return db.execute('SELECT * FROM downloads_catalog ORDER BY title').fetchall()
    def entries(self):
        with self.store.connect() as db:details={(r['kind'],r['item']):dict(r) for r in db.execute('SELECT * FROM downloads_details')}
        entries=[]
        for kind,rows in [('link',self.catalog()),('file',self.files())]:
            for row in rows:
                key=str(row['id']) if kind=='link' else row['name']
                item={'kind':kind,'item':key,'title':row['title'] if kind=='link' else key,'version':row['version'] if kind=='link' else '', 'platform':row['platform'] if kind=='link' else '', 'description':'','category':None,'url':row['url'] if kind=='link' else '/files/downloads/'+quote(key),'size':row['size'] if kind=='file' else None}
                item.update(details.get((kind,key),{}));entries.append(item)
        return sorted(entries,key=lambda r:r['title'].lower())
    def save_details(self,data):
        kind,item=data.get('kind'),data.get('item')
        if not any(r['kind']==kind and r['item']==item for r in self.entries()):raise ValueError('Download no longer exists.')
        title=data.get('title','').strip()
        if not title or len(title)>100:raise ValueError('Enter a title of at most 100 characters.')
        values=(kind,item,title,data.get('version','')[:80],data.get('platform','')[:80],data.get('description','')[:1000],self.category(data.get('category','')))
        with self.store.connect() as db:db.execute('INSERT OR REPLACE INTO downloads_details VALUES(?,?,?,?,?,?,?)',values)
    def select(self,current=None):
        return '<select name="category"><option value="">Uncategorized</option>'+''.join('<option value="'+str(r['id'])+'"'+(' selected' if current==r['id'] else '')+'>'+E(r['name'])+'</option>' for r in self.categories())+'</select>'
    def render(self,selected='',search=''):
        entries=self.entries();categories=self.categories();search=search.strip()[:100]
        if selected:
            if selected=='uncategorized':entries=[r for r in entries if r['category'] is None]
            else:entries=[r for r in entries if str(r['category'])==selected]
        if search:entries=[r for r in entries if search.lower() in ' '.join(str(r[k] or '') for k in ('title','platform','description','version')).lower()]
        content='<p>Browse internal tools and applications. Choose a download compatible with your machine.</p><form method="get" class="download-filter"><label for="download-search">Search applications</label><input id="download-search" name="q" value="'+E(search)+'" maxlength="100"><label for="download-category">Category</label><select id="download-category" name="category"><option value="">All categories</option>'
        for key,name in [('uncategorized','Uncategorized')]+[(str(r['id']),r['name']) for r in categories]:content+='<option value="'+key+'"'+(' selected' if selected==key else '')+'>'+E(name)+'</option>'
        content+='</select><button>Browse</button></form><div class="download-grid">'
        names={r['id']:r['name'] for r in categories}
        for item in entries:
            size=(' · '+self.size(item['size'])) if item['size'] is not None else ''
            content+='<article class="download-card"><span class="download-category">'+E(names.get(item['category'],'Uncategorized'))+'</span><h2>'+E(item['title'])+'</h2><p class="download-meta">'+E(' · '.join(v for v in [item['platform'],item['version']] if v))+E(size)+'</p><p>'+E(item['description'] or 'Download this internal tool or application.')+'</p><a class="button" href="'+E(item['url'])+'">Download</a></article>'
        return content+('</div>' if entries else '</div><p class="notice">No downloads match this selection.</p>')

def page(app,path,method,data,user,env,send):
    if path=='/downloads':
        query=parse_qs(env.get('QUERY_STRING',''))
        return send('200 OK',app.page('Download Center',app.downloads.render(query.get('category',[''])[0],query.get('q',[''])[0]),user))

def admin_render(app,user,services):
    library=app.downloads;csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
    content='<h2>Categories</h2><p>Deleting a category keeps its downloads and moves them to Uncategorized.</p><form method="post" class="download-filter">'+csrf+'<input name="name" maxlength="60" placeholder="New category name" aria-label="New category name" required><button name="action" value="save-category">Add category</button></form>'
    for row in library.categories():content+='<form method="post" class="download-filter">'+csrf+'<input type="hidden" name="category" value="'+str(row['id'])+'"><input name="name" value="'+E(row['name'])+'" maxlength="60" aria-label="Category name" required><button name="action" value="save-category">Rename</button><button name="action" value="remove-category">Delete category</button></form>'
    content+='<details><summary>Add download link</summary><form method="post" class="panel">'+csrf
    for key,label in [('title','Application / tool name'),('version','Version'),('platform','Operating system / platform'),('url','Download URL'),('description','Description')]:content+='<label>'+label+'</label><input name="'+key+'"'+(' type="url"' if key=='url' else '')+(' required' if key in ('title','url') else '')+'>'
    content+='<label>Category</label>'+library.select()+'<button name="action" value="add-link">Add download link</button></form></details><details><summary>Upload a tool or application</summary><form action="/admin/downloads/upload" method="post" enctype="multipart/form-data" class="panel">'+csrf+'<label>Package file</label><input name="file" type="file" required><button>Upload package</button></form><p>After uploading, set the title, category and description below. Downloads are available to guests.</p></details><h2>Manage applications</h2>'
    for item in library.entries():
        content+='<details class="download-editor"><summary>'+E(item['title'])+(' · '+library.size(item['size']) if item['size'] is not None else ' · External link')+'</summary><form method="post" class="panel">'+csrf+'<input type="hidden" name="kind" value="'+item['kind']+'"><input type="hidden" name="item" value="'+E(item['item'])+'">'
        for key,label in [('title','Application name'),('version','Version'),('platform','Platform'),('description','Description')]:content+='<label>'+label+'</label><input name="'+key+'" value="'+E(item[key])+'"'+(' required maxlength="100"' if key=='title' else '')+'>'
        content+='<label>Category</label>'+library.select(item['category'])+'<button name="action" value="save-details">Save application</button>'
        if item['kind']=='link':content+='<button name="action" value="remove-link">Remove link</button>'
        else:content+='<label class="download-delete-confirm"><input type="checkbox" name="confirm" value="yes"> Permanently delete this uploaded file</label><button name="action" value="remove-file">Delete file</button>'
        content+='</form></details>'
    return content

def admin_change(app,data,services):
    action=data.get('action');library=app.downloads
    if action=='remove-link':library.remove_link(data.get('item',data.get('link','')))
    elif action=='remove-file':library.remove_file(data)
    elif action=='save-category':library.save_category(data)
    elif action=='remove-category':library.remove_category(data.get('category',''))
    elif action=='save-details':library.save_details(data)
    elif action in ('add-link',None):library.add_link(data)
    else:raise ValueError('Choose a download catalog action.')
    return 'Download catalog saved.'

def resource(app,name):return DownloadLibrary(app.store,app.config,app.modules,'downloads')
