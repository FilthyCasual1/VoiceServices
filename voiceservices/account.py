"""Profile, security, sessions and addon-linked identities in the core account page."""
import html,re,time
from datetime import datetime,timezone
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
E=lambda value:html.escape(str(value),quote=True)
def initialize(app):
    with app.store.connect() as db: db.execute("CREATE TABLE IF NOT EXISTS account_profiles(user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,email TEXT NOT NULL DEFAULT '',phone TEXT NOT NULL DEFAULT '',timezone TEXT NOT NULL DEFAULT 'UTC')")
def initialize_extras(app):
    with app.store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS account_photos(user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,image BLOB NOT NULL,mime TEXT NOT NULL)')
        db.execute("CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,title TEXT NOT NULL,body TEXT NOT NULL,created INTEGER NOT NULL,is_read INTEGER NOT NULL DEFAULT 0)")
        db.execute("CREATE TABLE IF NOT EXISTS inbox_initialized(user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE)")
def notify(app,user_id,title,body):
    with app.store.connect() as db:
        db.execute('INSERT INTO notifications(user_id,title,body,created) VALUES(?,?,?,?)',(user_id,title[:120],body[:5000],int(time.time())))
def inbox(app,user):
    with app.store.connect() as db:
        if not db.execute('SELECT 1 FROM inbox_initialized WHERE user_id=?',(user['id'],)).fetchone():
            db.execute('INSERT INTO inbox_initialized VALUES(?)',(user['id'],))
            db.execute('INSERT INTO notifications(user_id,title,body,created) VALUES(?,?,?,?)',(user['id'],'Welcome to your inbox','Account and service notifications will appear here.',int(time.time())))
        return [dict(r) for r in db.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY created DESC,id DESC',(user['id'],))]
def photo(app,user):
    with app.store.connect() as db:
        row=db.execute('SELECT image,mime FROM account_photos WHERE user_id=?',(user['id'],)).fetchone()
        return (bytes(row[0]),row[1]) if row else None
def upload_photo(app,user,raw):
    from .branding import image_type
    suffix=image_type(raw)
    with app.store.connect() as db: db.execute('INSERT OR REPLACE INTO account_photos VALUES(?,?,?)',(user['id'],raw,'image/png' if suffix=='png' else 'image/jpeg'))
    notify(app,user['id'],'Profile picture updated','Your new profile picture is now in use.')
def profile(app,user):
    with app.store.connect() as db:
        row=db.execute('SELECT * FROM account_profiles WHERE user_id=?',(user['id'],)).fetchone()
        return dict(row) if row else {'email':'','phone':'','timezone':'UTC'}
def change(app,user,data,token):
    action=data.get('action')
    if action=='remove-photo':
        with app.store.connect() as db: db.execute('DELETE FROM account_photos WHERE user_id=?',(user['id'],))
        return 'Profile picture removed.'
    if action in ('read-notification','delete-notification'):
        try: key=int(data.get('notification',''))
        except ValueError: raise ValueError('Choose a notification.')
        with app.store.connect() as db:
            if action=='read-notification': db.execute('UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?',(key,user['id']))
            else: db.execute('DELETE FROM notifications WHERE id=? AND user_id=?',(key,user['id']))
        return 'Inbox updated.'
    if action=='profile':
        name=data.get('display_name','').strip();email=data.get('email','').strip();phone=data.get('phone','').strip();tz=data.get('timezone','UTC').strip() or 'UTC'
        if len(name)>100 or len(email)>254 or (email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email)) or len(phone)>40 or (phone and not re.fullmatch(r'[+0-9() .-]+',phone)): raise ValueError('Check display name, email address and contact number.')
        try: ZoneInfo(tz)
        except (ZoneInfoNotFoundError,ValueError): raise ValueError('Use an IANA time zone such as UTC or America/Chicago.')
        with app.store.connect() as db:
            db.execute('UPDATE users SET display_name=? WHERE id=?',(name,user['id']))
            db.execute('INSERT OR REPLACE INTO account_profiles VALUES(?,?,?,?)',(user['id'],email,phone,tz))
        return 'Profile saved.'
    if action=='revoke-sessions':
        with app.store.connect() as db: db.execute('DELETE FROM sessions WHERE user_id=? AND token!=?',(user['id'],token))
        return 'Other sessions signed out.'
    from .modules import CATALOG
    for key in CATALOG:
        if app.modules.installed(key):
            handler=getattr(app.modules.load(key),'account_action',None)
            if handler:
                result=handler(app,user,data)
                if result is not None: return result
    raise ValueError('Unknown account action.')
def render(app,user,token,note=''):
    from .administration import password_form
    from .modules import CATALOG
    csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">';value=profile(app,user)
    content='<p><a href="#profile">Profile</a> | <a href="#inbox">Inbox</a> | <a href="#security">Security</a> | <a href="#sessions">Sessions</a> | <a href="#services">Linked services</a></p>'
    if note: content+='<p class="notice">'+E(note)+'</p>'
    content+='<div class="panel profile-picture"><img class="avatar" src="/account/photo" alt="Profile picture"><form action="/account/photo/upload" method="post" enctype="multipart/form-data">'+csrf+'<label>Profile picture (PNG or JPEG, up to 1 MiB)</label><input type="file" name="file" accept="image/png,image/jpeg" required><br><button>Upload picture</button></form><form method="post">'+csrf+'<button name="action" value="remove-photo">Remove picture</button></form></div>'
    content+='<h2 id="inbox">Notification inbox</h2>'
    messages=inbox(app,user)
    if not messages: content+='<p>Your inbox is empty.</p>'
    for message in messages:
        content+='<div class="panel"><strong>'+E(message['title'])+'</strong> '+('' if message['is_read'] else '<span class="muted">Unread</span>')+'<p>'+E(message['body']).replace('\n','<br>')+'</p><small>'+E(datetime.fromtimestamp(message['created'],timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))+'</small><form method="post">'+csrf+'<input type="hidden" name="notification" value="'+str(message['id'])+'"><button name="action" value="read-notification">Mark read</button><button name="action" value="delete-notification">Delete</button></form></div>'
    content+='<h2 id="profile">Your profile</h2><div class="panel"><p>Username: <strong>'+E(user['username'])+'</strong><br>Access: '+E(user['role'])+'<br>Authentication: '+('Alpine system account' if app.store.accounts else 'Local portal account')+'</p><form method="post">'+csrf+'<input name="action" type="hidden" value="profile">'
    for key,label,entry in [('display_name','Display name',user['display_name']),('email','Email address',value['email']),('phone','Contact number',value['phone']),('timezone','Time zone',value['timezone'])]: content+='<label>'+label+'</label><input name="'+key+'" value="'+E(entry or '')+'">'
    content+='<br><button>Save profile</button></form></div><h2 id="security">Password and security</h2>'+password_form(user)+'<h2 id="sessions">Active sessions</h2><table><tr><th>Session</th><th>Expires (UTC)</th></tr>'
    with app.store.connect() as db:
        for row in db.execute('SELECT token,expires FROM sessions WHERE user_id=? AND expires>? ORDER BY expires DESC',(user['id'],int(time.time()))):
            content+='<tr><td>'+('This session' if row['token']==token else 'Other session')+'</td><td>'+E(datetime.fromtimestamp(row['expires'],timezone.utc).strftime('%Y-%m-%d %H:%M'))+'</td></tr>'
    content+='</table><form method="post">'+csrf+'<button name="action" value="revoke-sessions">Sign out other sessions</button></form><h2 id="services">Linked services</h2>'
    panels=[]
    for key,(title,_) in CATALOG.items():
        if app.modules.installed(key):
            provider=app.modules.load(key);hook=getattr(provider,'account_panel',None)
            if hook: panels.append(hook(app,user))
    content+=''.join(panels) if panels else '<p>No installed service has linked an identity to your account.</p>'
    return content
