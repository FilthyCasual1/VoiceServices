"""Profile, security, sessions and addon-linked identities in the core account page."""
import html,re,time
from datetime import datetime,timezone
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
E=lambda value:html.escape(str(value),quote=True)
def initialize(app):
    with app.store.connect() as db: db.execute("CREATE TABLE IF NOT EXISTS account_profiles(user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,email TEXT NOT NULL DEFAULT '',phone TEXT NOT NULL DEFAULT '',timezone TEXT NOT NULL DEFAULT 'UTC')")
def profile(app,user):
    with app.store.connect() as db:
        row=db.execute('SELECT * FROM account_profiles WHERE user_id=?',(user['id'],)).fetchone()
        return dict(row) if row else {'email':'','phone':'','timezone':'UTC'}
def change(app,user,data,token):
    action=data.get('action')
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
    content='<p><a href="#profile">Profile</a> | <a href="#security">Security</a> | <a href="#sessions">Sessions</a> | <a href="#services">Linked services</a></p>'
    if note: content+='<p class="notice">'+E(note)+'</p>'
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
