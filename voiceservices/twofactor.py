"""Authenticator enrollment and short-lived, single-use login challenges."""
import hashlib,html,io,json,secrets,time
import pyotp,segno
E=lambda v:html.escape(str(v),quote=True)
H=lambda v:hashlib.sha256(v.encode()).hexdigest()
def initialize(app):
    with app.store.connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS twofactor(user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,secret TEXT NOT NULL DEFAULT '',pending TEXT NOT NULL DEFAULT '',pending_until INTEGER NOT NULL DEFAULT 0,pending_session TEXT NOT NULL DEFAULT '',last_counter INTEGER NOT NULL DEFAULT -1,recovery TEXT NOT NULL DEFAULT '[]',failures INTEGER NOT NULL DEFAULT 0,blocked_until INTEGER NOT NULL DEFAULT 0)")
        db.execute('CREATE TABLE IF NOT EXISTS factor_challenges(token TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,csrf TEXT NOT NULL,expires INTEGER NOT NULL,attempts INTEGER NOT NULL DEFAULT 0)')
        if 'remember' not in {r[1] for r in db.execute('PRAGMA table_info(factor_challenges)')}: db.execute('ALTER TABLE factor_challenges ADD COLUMN remember INTEGER NOT NULL DEFAULT 0')
def state(app,user):
    with app.store.connect() as db:
        row=db.execute('SELECT * FROM twofactor WHERE user_id=?',(user['id'],)).fetchone()
        return dict(row) if row else {}
def check(db,user_id,code,secret=None):
    row=db.execute('SELECT * FROM twofactor WHERE user_id=?',(user_id,)).fetchone();now=int(time.time())
    if not row or row['blocked_until']>now: return False
    if row['blocked_until'] and row['blocked_until']<=now: db.execute('UPDATE twofactor SET failures=0,blocked_until=0 WHERE user_id=?',(user_id,))
    value=code.strip().replace(' ','');counter=now//30;matched=None
    seed=secret or row['secret']
    if seed:
        for step in (counter-1,counter,counter+1):
            if step>row['last_counter'] and secrets.compare_digest(pyotp.TOTP(seed).at(step*30),value): matched=step;break
    if matched is not None:
        db.execute('UPDATE twofactor SET last_counter=?,failures=0,blocked_until=0 WHERE user_id=?',(matched,user_id));return True
    if secret is None:
        codes=json.loads(row['recovery']);digest=H(value.upper())
        if digest in codes:
            codes.remove(digest);db.execute('UPDATE twofactor SET recovery=?,failures=0,blocked_until=0 WHERE user_id=?',(json.dumps(codes),user_id));return True
    failures=(0 if row['blocked_until'] and row['blocked_until']<=now else row['failures'])+1
    db.execute('UPDATE twofactor SET failures=?,blocked_until=? WHERE user_id=?',(failures,now+300 if failures>=10 else 0,user_id));return False
def password(app,user,value):
    token=app.store.login(user['username'],value)
    if not token: raise ValueError('Current password is incorrect.')
    app.store.logout(token)
def change(app,user,data,token):
    action=data.get('action');current=state(app,user)
    if action=='factor-start':
        password(app,user,data.get('current_password',''))
        if current.get('secret'): raise ValueError('Two-factor authentication is already enabled.')
        with app.store.connect() as db:
            db.execute('INSERT OR IGNORE INTO twofactor(user_id) VALUES(?)',(user['id'],))
            db.execute('UPDATE twofactor SET pending=?,pending_until=?,pending_session=? WHERE user_id=?',(pyotp.random_base32(),int(time.time())+600,H(token),user['id']))
        return 'Scan the QR code and enter a current authenticator code to finish setup.'
    if action=='factor-confirm':
        if not current.get('pending') or current['pending_until']<time.time() or current['pending_session']!=H(token): raise ValueError('Setup expired. Start again.')
        codes=[secrets.token_hex(8).upper() for _ in range(10)]
        with app.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            valid=check(db,user['id'],data.get('code',''),current['pending'])
            if valid:
                db.execute("UPDATE twofactor SET secret=pending,pending='',pending_until=0,pending_session='',recovery=? WHERE user_id=?",(json.dumps([H(c) for c in codes]),user['id']))
                db.execute('DELETE FROM sessions WHERE user_id=? AND token!=?',(user['id'],token))
                db.execute('DELETE FROM factor_challenges WHERE user_id=?',(user['id'],))
        if not valid: raise ValueError('Code incorrect, already used, or temporarily locked. Wait for a new code and try again.')
        from .account import notify
        notify(app,user['id'],'Two-factor authentication enabled','Authenticator codes are now required to sign in.')
        return 'Two-factor authentication enabled. Save these single-use recovery codes now; they are shown only once: '+', '.join(codes)
    if action=='factor-disable':
        password(app,user,data.get('current_password',''))
        with app.store.connect() as db:
            db.execute('BEGIN IMMEDIATE');valid=check(db,user['id'],data.get('code',''))
            if valid:
                db.execute('DELETE FROM twofactor WHERE user_id=?',(user['id'],));db.execute('DELETE FROM factor_challenges WHERE user_id=?',(user['id'],));db.execute('DELETE FROM sessions WHERE user_id=? AND token!=?',(user['id'],token))
        if not valid: raise ValueError('Enter a fresh authenticator code or unused recovery code.')
        from .account import notify
        notify(app,user['id'],'Two-factor authentication disabled','Your account no longer requires an authenticator code.')
        return 'Two-factor authentication disabled.'
    return None
def panel(app,user,token):
    row=state(app,user);csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
    content='<h2>Two-factor authentication</h2><div class="panel"><p>Use Google Authenticator or another TOTP app for rotating six-digit codes.</p>'
    if row.get('secret'):
        content+='<p><strong>Enabled</strong> · '+str(len(json.loads(row['recovery'])))+' recovery codes remaining.</p><form method="post">'+csrf+'<label>Current password</label><input name="current_password" type="password" autocomplete="current-password" required><label>Authenticator or recovery code</label><input name="code" autocomplete="one-time-code" required><br><button name="action" value="factor-disable">Disable two-factor authentication</button></form>'
    elif row.get('pending') and row['pending_until']>time.time() and row['pending_session']==H(token):
        content+='<img class="factor-qr" src="/account/twofactor/qr" alt="Scan with your authenticator"><p>Manual setup key: <code>'+E(row['pending'])+'</code></p><form method="post">'+csrf+'<label>Six-digit authenticator code</label><input name="code" inputmode="numeric" pattern="[0-9]{6}" autocomplete="one-time-code" required><br><button name="action" value="factor-confirm">Confirm and enable</button></form>'
    else:
        content+='<p>Not enabled. Confirm your password to begin setup.</p><form method="post">'+csrf+'<label>Current password</label><input name="current_password" type="password" autocomplete="current-password" required><br><button name="action" value="factor-start">Set up authenticator</button></form>'
    return content+'</div>'
def qr(app,user,token):
    row=state(app,user)
    if not row.get('pending') or row['pending_until']<time.time() or row['pending_session']!=H(token): return None
    uri=pyotp.TOTP(row['pending']).provisioning_uri(name=user['username'],issuer_name='CasualNetworks ServiceReady')
    output=io.BytesIO();segno.make(uri,micro=False).save(output,kind='png',scale=5,border=4);return output.getvalue()
def challenge(app,user,remember=False):
    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24)
    with app.store.connect() as db:
        db.execute('DELETE FROM factor_challenges WHERE expires<?',(int(time.time()),))
        db.execute('INSERT INTO factor_challenges(token,user_id,csrf,expires,remember) VALUES(?,?,?,?,?)',(H(token),user['id'],csrf,int(time.time())+300,int(remember)))
    return token
def finish(app,token,csrf,code):
    with app.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM factor_challenges WHERE token=?',(H(token),)).fetchone()
        if not row or row['expires']<time.time() or row['attempts']>=10 or not secrets.compare_digest(row['csrf'],csrf): return None
        db.execute('UPDATE factor_challenges SET attempts=attempts+1 WHERE token=?',(H(token),))
        if not check(db,row['user_id'],code): return None
        session=secrets.token_urlsafe(32)
        db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(session,row['user_id'],secrets.token_urlsafe(24),int(time.time())+(2592000 if row['remember'] else 28800)))
        db.execute('DELETE FROM factor_challenges WHERE user_id=?',(row['user_id'],))
        return session
def login_page(app,token,error=''):
    with app.store.connect() as db: row=db.execute('SELECT * FROM factor_challenges WHERE token=? AND expires>? AND attempts<10',(H(token),int(time.time()))).fetchone()
    if not row: return '<p class="notice error">Your sign-in attempt expired. <a href="/login">Start again</a>.</p>'
    return ('<p class="notice error">'+E(error)+'</p>' if error else '')+'<div class="panel login"><p>Enter the code from your authenticator, or an unused recovery code.</p><form method="post"><input type="hidden" name="csrf" value="'+E(row['csrf'])+'"><label>Authenticator or recovery code</label><input name="code" autocomplete="one-time-code" required><br><button>Verify and sign in</button></form><p><a href="/login">Start again</a></p></div>'
