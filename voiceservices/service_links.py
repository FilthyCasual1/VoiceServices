"""Account linking requests; identity operations remain owned by service addons."""
import html,time
from .modules import CATALOG
E=lambda v:html.escape(str(v),quote=True)
def initialize(app):
 with app.store.connect() as db:db.execute('CREATE TABLE IF NOT EXISTS service_link_requests(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,module TEXT NOT NULL,identity TEXT NOT NULL,state TEXT NOT NULL,created INTEGER NOT NULL,UNIQUE(user_id,module))')
def providers(app):
 return {key:app.modules.load(key) for key in CATALOG if app.modules.installed(key) and callable(getattr(app.modules.load(key),'account_link',None))}
def request(app,user,data):
 initialize(app);key=data.get('module','');identity=data.get('identity','').strip()
 if key not in providers(app):raise ValueError('Choose an installed service supporting account links.')
 if not identity or len(identity)>128 or any(ord(c)<32 for c in identity):raise ValueError('Enter a service account ID of at most 128 characters.')
 with app.store.connect() as db:
  db.execute("INSERT INTO service_link_requests(user_id,module,identity,state,created) VALUES(?,?,?,'pending',?) ON CONFLICT(user_id,module) DO UPDATE SET identity=excluded.identity,state='pending',created=excluded.created",(user['id'],key,identity,int(time.time())))
 return 'Service link requested. An administrator will review the account ID before linking it.'
def review(app,user,data):
 if user['role']!='admin':raise PermissionError('Administrator access required.')
 initialize(app)
 try:identifier=int(data.get('request',''))
 except ValueError:raise ValueError('Choose a service link request.')
 with app.store.connect() as db:row=db.execute('SELECT r.*,u.username FROM service_link_requests r JOIN users u ON u.id=r.user_id WHERE r.id=?',(identifier,)).fetchone()
 if not row or row['state']!='pending':raise ValueError('This request is no longer pending.')
 state='rejected'
 if data.get('action')=='approve-service-link':
  provider=providers(app).get(row['module'])
  if not provider:raise ValueError('Install the service addon before approving its link.')
  provider.account_link(app,dict(row),row['identity']);state='approved'
 with app.store.connect() as db:
  db.execute('UPDATE service_link_requests SET state=? WHERE id=?',(state,identifier))
  db.execute('INSERT INTO audit(at,user_id,action) VALUES(?,?,?)',(int(time.time()),user['id'],'Service link '+state+': '+row['username']+' / '+row['module']))
 return 'Service link '+state+'.'
def panel(app,user):
 initialize(app);available=providers(app);csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
 text='<div class="panel"><h3>Link a service account</h3><p>Request a link to an existing service identity. Your administrator reviews ownership and access before approving. Do not enter a password.</p>'
 if available:
  text+='<form method="post">'+csrf+'<label>Service</label><select name="module">'+''.join('<option value="'+key+'">'+E(CATALOG[key][0])+'</option>' for key in available)+'</select><label>Service account ID</label><input name="identity" maxlength="128" required><button name="action" value="request-service-link">Request link</button></form>'
 else:text+='<p>No installed addon currently provides account linking.</p>'
 with app.store.connect() as db:
  for row in db.execute('SELECT * FROM service_link_requests WHERE user_id=? ORDER BY created DESC',(user['id'],)):text+='<p>'+E(CATALOG.get(row['module'],(row['module'],))[0])+' · '+E(row['identity'])+' · '+E(row['state'].title())+'</p>'
 return text+'</div>'
def admin_panel(app,user):
 initialize(app);csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
 text='<details class="settings-section" id="service-links"><summary>Service account link requests</summary><p>Verify the requester owns the remote account before approving. Approval maps identities; remote profile verification remains with the service addon.</p>'
 with app.store.connect() as db:rows=db.execute("SELECT r.*,u.username FROM service_link_requests r JOIN users u ON u.id=r.user_id WHERE state='pending' ORDER BY created").fetchall()
 if not rows:text+='<p>No pending service link requests.</p>'
 for row in rows:text+='<div class="panel"><strong>'+E(row['username'])+'</strong> · '+E(CATALOG.get(row['module'],(row['module'],))[0])+' · '+E(row['identity'])+'<form method="post">'+csrf+'<input type="hidden" name="request" value="'+str(row['id'])+'"><button name="action" value="approve-service-link">Approve link</button><button name="action" value="reject-service-link">Reject</button></form></div>'
 return text+'</details>'
