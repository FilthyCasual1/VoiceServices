"""Administrator-reviewed recovery with expiring single-use tokens."""
import hashlib,html,secrets,time
from . import twofactor
E=lambda v:html.escape(str(v),quote=True)
def initialize(app):
    with app.store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS recovery_requests(id INTEGER PRIMARY KEY,username TEXT NOT NULL,contact TEXT NOT NULL,details TEXT NOT NULL,created INTEGER NOT NULL,closed INTEGER NOT NULL DEFAULT 0)')
        db.execute('CREATE TABLE IF NOT EXISTS recovery_tokens(token TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,expires INTEGER NOT NULL,reset_factor INTEGER NOT NULL)')
def issue(app,actor,data):
    if actor['role']!='admin': raise PermissionError('Administrator access required.')
    twofactor.password(app,actor,data.get('current_password',''))
    if data.get('verified')!='yes': raise ValueError('Verify the account owner before authorizing recovery.')
    with app.store.connect() as db:
        user=db.execute('SELECT * FROM users WHERE username=?',(data.get('username','').strip(),)).fetchone()
        if not user: raise ValueError('Account unavailable.')
        token=secrets.token_urlsafe(32)
        db.execute('DELETE FROM recovery_tokens WHERE user_id=?',(user['id'],))
        db.execute('INSERT INTO recovery_tokens VALUES(?,?,?,?)',(twofactor.H(token),user['id'],int(time.time())+1800,int(data.get('reset_factor')=='yes')))
        db.execute('UPDATE recovery_requests SET closed=1 WHERE username=?',(user['username'],))
        db.execute('INSERT INTO audit(at,user_id,action) VALUES(?,?,?)',(int(time.time()),actor['id'],'Authorized account recovery for '+user['username']))
    return 'Recovery authorized. Deliver this single-use code securely to the verified owner; it expires in 30 minutes: '+token

def reset(app,data):
    new=data.get('new_password','')
    if not 12<=len(new)<=1024 or new!=data.get('confirm_password'): raise ValueError('Use matching passwords of 12–1024 characters.')
    with app.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT recovery_tokens.*,users.username FROM recovery_tokens JOIN users ON users.id=user_id WHERE token=? AND expires>?',(twofactor.H(data.get('recovery_code','').strip()),int(time.time()))).fetchone()
        if not row: raise ValueError('Recovery code invalid or expired. Contact your administrator.')
        if app.store.accounts: app.store.accounts.call('reset',row['username'],'',new)
        else:
            salt=secrets.token_hex(16);digest=hashlib.pbkdf2_hmac('sha256',new.encode(),salt.encode(),310000).hex()
            db.execute('UPDATE users SET password=? WHERE id=?',(salt+':'+digest,row['user_id']))
        for table in ('sessions','phones','factor_challenges'): db.execute('DELETE FROM '+table+' WHERE user_id=?',(row['user_id'],))
        if row['reset_factor']: db.execute('DELETE FROM twofactor WHERE user_id=?',(row['user_id'],))
        db.execute('DELETE FROM recovery_tokens WHERE user_id=?',(row['user_id'],))
        db.execute('INSERT INTO audit(at,user_id,action) VALUES(?,?,?)',(int(time.time()),row['user_id'],'Completed account recovery'))
    from .account import notify
    notify(app,row['user_id'],'Account recovered','Your password was reset through administrator-approved recovery.')
    return 'Password reset. Sign in with your new password. Your existing authenticator is still required unless its recovery was explicitly authorized.'
def public(app,env,data,cookie,method,send):
    nonce=cookie['vs_recover'].value if 'vs_recover' in cookie else '';note='';status='200 OK'
    if method=='POST':
        if not nonce or not secrets.compare_digest(nonce,data.get('csrf','')): return send('403 Forbidden','Recovery form expired. Reload the page and try again.')
        key='recover:'+env.get('REMOTE_ADDR','unknown');now=time.time();count,at=app.attempts.get(key,(0,now))
        if at<now-900: count=0;at=now
        if count>=5: return send('429 Too Many Requests','Please wait 15 minutes before making another recovery attempt.')
        app.attempts[key]=(count+1,at)
        try:
            if data.get('action')=='reset': note=reset(app,data)
            else:
                username=data.get('username','').strip();contact=data.get('contact','').strip();details=data.get('details','').strip()
                if not 1<=len(username)<=64 or not 1<=len(contact)<=254 or len(details)>2000: raise ValueError('Enter your username and contact details.')
                with app.store.connect() as db: db.execute('INSERT INTO recovery_requests(username,contact,details,created) VALUES(?,?,?,?)',(username,contact,details,int(now)))
                note='Your request has been recorded for administrator review. Contact your administrator to verify ownership; submitting a request does not reset an account.'
        except ValueError as exc: note=str(exc);status='400 Bad Request'
    nonce=secrets.token_urlsafe(32);csrf='<input type="hidden" name="csrf" value="'+E(nonce)+'">'
    content='<div class="recovery-page">'+('<p class="notice">'+E(note)+'</p>' if note else '')+'<p>Forgot your password or lost your authenticator? Request help from your administrator. Recovery requires verification of account ownership.</p><h2>Request account recovery</h2><div class="panel"><form method="post">'+csrf+'<label>Username</label><input name="username" maxlength="64" autocomplete="username" required><label>How your administrator can contact you</label><input name="contact" maxlength="254" required><label>Details (optional)</label><textarea name="details" maxlength="2000" rows="3"></textarea><br><button name="action" value="request">Submit recovery request</button></form></div><h2>Use an approved recovery code</h2><div class="panel"><form method="post">'+csrf+'<label>Recovery code provided by your administrator</label><input name="recovery_code" autocomplete="off" required><label>New password</label><input name="new_password" type="password" minlength="12" autocomplete="new-password" required><label>Confirm password</label><input name="confirm_password" type="password" minlength="12" autocomplete="new-password" required><br><button name="action" value="reset">Reset password</button></form></div><p><a href="/login">Return to sign in</a></p></div>'
    return send(status,app.page('Recover your account',content,None),extra=[('Set-Cookie',f'vs_recover={nonce}; HttpOnly; SameSite=Lax; Path=/recover; Max-Age=900'+('; Secure' if app.secure else ''))])
def render(app,user):
    with app.store.connect() as db: rows=db.execute('SELECT * FROM recovery_requests WHERE closed=0 ORDER BY created DESC LIMIT 100').fetchall()
    content='<p>Verify ownership outside the portal before issuing a recovery code. No reset email is sent automatically.</p><table><tr><th>Requested account</th><th>Contact</th><th>Details</th></tr>'+''.join('<tr><td>'+E(r['username'])+'</td><td>'+E(r['contact'])+'</td><td>'+E(r['details'])+'</td></tr>' for r in rows)+'</table><h2>Authorize recovery</h2><div class="panel"><form method="post"><input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><label>Verified account username</label><input name="username" required><label>Your current administrator password</label><input name="current_password" type="password" autocomplete="current-password" required><label><input type="checkbox" name="verified" value="yes" required> I verified account ownership</label><label><input type="checkbox" name="reset_factor" value="yes"> Also reset a lost authenticator</label><button>Issue single-use recovery code</button></form></div>'
    return content
