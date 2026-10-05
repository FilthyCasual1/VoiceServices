import html,json,time
from urllib.parse import urlencode,urlsplit
E=lambda value:html.escape(str(value),quote=True)
from voiceservices.library import Library
from urllib.parse import urlsplit
class DownloadLibrary(Library):
    def __init__(self,*args):
        super().__init__(*args)
        with self.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS downloads_catalog(id INTEGER PRIMARY KEY,title TEXT,version TEXT,platform TEXT,url TEXT)')
    def add_link(self,data):
        url=data.get('url','');parsed=urlsplit(url)
        if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or parsed.password or any(ord(c)<33 for c in url): raise ValueError('Enter a valid HTTP(S) download URL without credentials or whitespace.')
        title=data.get('title','').strip()
        if not title or len(title)>100: raise ValueError('Enter a title of at most 100 characters.')
        with self.store.connect() as db: db.execute('INSERT INTO downloads_catalog(title,version,platform,url) VALUES(?,?,?,?)',(title,data.get('version','')[:80],data.get('platform','')[:80],url))
    def remove_link(self,value):
        with self.store.connect() as db: db.execute('DELETE FROM downloads_catalog WHERE id=?',(int(value),))
    def catalog(self):
        with self.store.connect() as db: return db.execute('SELECT * FROM downloads_catalog ORDER BY title').fetchall()
    def render(self):
        content='<p class="notice">Download internal tools and applications for your machines. Choose a package compatible with your operating system.</p><h2>Tools and applications</h2><table><tr><th>Application</th><th>Version</th><th>Platform</th><th>Download</th></tr>'
        for item in self.catalog(): content+='<tr><td>'+E(item['title'])+'</td><td>'+E(item['version'])+'</td><td>'+E(item['platform'])+'</td><td><a href="'+E(item['url'])+'">Download</a></td></tr>'
        for item in self.files(): content+='<tr><td>'+E(item['name'])+'</td><td>Operator supplied</td><td>See package documentation</td><td><a href="/files/downloads/'+E(item['name'])+'">Download</a></td></tr>'
        return content+'</table>'


def page(app,path,method,data,user,env,send):
    if path=="/downloads": return send("200 OK",app.page("Download Center",app.downloads.render(),user))

def admin_render(app,user,services):
    csrf='<input type="hidden" name="csrf" value="'+E(user["csrf"])+'">'
    content=""
    content+='<div class="panel"><form method="post">'+csrf
    for key,label in [('title','Application / tool name'),('version','Version'),('platform','Operating system / platform'),('url','Download URL')]: content+='<label>'+label+'</label><input name="'+key+'"'+(' type="url"' if key=='url' else '')+' required>'
    content+='<br><button>Add download link</button></form></div><h2>Catalog links</h2><table><tr><th>Title</th><th>Action</th></tr>'
    for item in app.downloads.catalog(): content+='<tr><td>'+E(item['title'])+'</td><td><form method="post">'+csrf+'<input type="hidden" name="link" value="'+str(item['id'])+'"><button name="action" value="remove-link">Remove link</button></form></td></tr>'
    content+='</table><h2>Upload a tool or application</h2><div class="panel"><form action="/admin/downloads/upload" method="post" enctype="multipart/form-data">'+csrf+'<label>Package file</label><input name="file" type="file" required><br><button>Upload package</button></form><p>Uploaded packages and catalog links are available to guests in Downloads. Use this module for files intended for your internal network.</p></div>'+app.downloads.render()
    return content

def admin_change(app,data,services):
    action=data.get("action")
    if action=='remove-link': app.downloads.remove_link(data.get('link',''))
    else: app.downloads.add_link(data)
    note='Download catalog saved.'
    return locals().get("note","Settings saved.")

def resource(app,name): return DownloadLibrary(app.store,app.config,app.modules,"downloads")
