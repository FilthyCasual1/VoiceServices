"""Invitation-gated registration and guided account setup."""
import hashlib,html,re,secrets,time
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from . import regional
E=lambda value:html.escape(str(value),quote=True)
def invitation_action(app,actor,data):
    if actor['role']!='admin':raise PermissionError('Administrator access required.')
    with app.store.connect() as db:
        if data.get('action')=='invite-create':
            try:days=int(data.get('days','7'))
            except ValueError:raise ValueError('Choose a valid expiry.')
            if days not in (1,7,30):raise ValueError('Choose 1, 7 or 30 days.')
            code=secrets.token_urlsafe(24);digest=hashlib.sha256(code.encode()).hexdigest()
            db.execute('INSERT INTO invitations(digest,created,expires,issuer) VALUES(?,?,?,?)',(digest,int(time.time()),int(time.time())+days*86400,actor['id']))
            db.execute('INSERT INTO audit(at,user_id,action) VALUES(?,?,?)',(int(time.time()),actor['id'],'Created registration invitation'))
            return 'Invitation code (shown once): '+code+' — expires in '+str(days)+' days. Give this code to the new user.'
        if data.get('action')=='invite-revoke':
            db.execute('UPDATE invitations SET revoked=1 WHERE digest=? AND used_by IS NULL',(data.get('invitation',''),))
            return 'Invitation revoked.'
    raise ValueError('Choose an invitation action.')
def invitations(app,actor):
    csrf='<input type="hidden" name="csrf" value="'+E(actor['csrf'])+'">'
    text='<details class="settings-section"><summary>Account invitations</summary><div class="panel"><p>New users need a single-use code from an administrator. Codes expire and are displayed only when issued.</p><form method="post" class="invitation-create">'+csrf+'<label>Expires in <select name="days"><option value="1">1 day</option><option value="7" selected>7 days</option><option value="30">30 days</option></select></label><button name="action" value="invite-create">Create invitation</button></form><table><tr><th>Issued</th><th>Expires</th><th>Status</th><th>Action</th></tr>'
    with app.store.connect() as db:
        rows=db.execute('SELECT * FROM invitations ORDER BY created DESC LIMIT 100').fetchall()
    for row in rows:
        state='Used' if row['used_by'] is not None else 'Revoked' if row['revoked'] else 'Expired' if row['expires']<=time.time() else 'Available'
        text+='<tr><td>'+E(regional.format_timestamp(app,row['created']))+'</td><td>'+E(regional.format_timestamp(app,row['expires']))+'</td><td>'+state+'</td><td>'
        if state=='Available':text+='<form method="post">'+csrf+'<input type="hidden" name="invitation" value="'+E(row['digest'])+'"><button name="action" value="invite-revoke">Revoke</button></form>'
        text+='</td></tr>'
    return text+'</table></div></details>'
def profile(data,app):
    name=data.get('display_name','').strip();email=data.get('email','').strip();zone=data.get('timezone',regional.settings(app)['timezone'])
    if len(name)>100 or len(email)>254 or (email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email)):raise ValueError('Check your display name and email address.')
    try:ZoneInfo(zone)
    except (ValueError,ZoneInfoNotFoundError):raise ValueError('Choose a valid time zone.')
    return {'display_name':name,'email':email,'timezone':zone}
def form(app,nonce,data):
    value=lambda key:E(data.get(key,''))
    return ('<form method="post" data-onboarding><input type="hidden" name="csrf" value="'+E(nonce)+'"><ol class="tools-steps"><li data-onboard-marker="0" aria-current="step">Account</li><li data-onboard-marker="1">Profile</li><li data-onboard-marker="2">Review</li></ol>'
      '<fieldset data-onboard-step="0"><legend>Your account</legend><p>Get an invitation code from your administrator to get started.</p><label>Invitation code</label><input name="invitation" value="'+value('invitation')+'" autocomplete="off" required><label>Username</label><input name="username" value="'+value('username')+'" autocomplete="username" minlength="3" maxlength="64" required><label>Password</label><input name="password" type="password" autocomplete="new-password" minlength="12" required><label>Confirm password</label><input name="confirm_password" type="password" autocomplete="new-password" minlength="12" required><button type="button" data-onboard-next="1">Next →</button></fieldset>'
      '<fieldset data-onboard-step="1"><legend>Your profile</legend><p>These details help personalize your account. Name and email are optional.</p><label>Display name</label><input name="display_name" maxlength="100" value="'+value('display_name')+'" autocomplete="name"><label>Email address</label><input name="email" type="email" maxlength="254" value="'+value('email')+'" autocomplete="email"><label>Time zone</label>'+regional.timezone_select('timezone',data.get('timezone',regional.settings(app)['timezone']))+'<button type="button" data-onboard-next="0">← Back</button><button type="button" data-onboard-next="2">Next →</button></fieldset>'
      '<fieldset data-onboard-step="2"><legend>Ready to join</legend><p data-onboard-review></p><p>Your invitation will be used when the account is successfully created. You can finish your profile and set up two-factor authentication next.</p><button type="button" data-onboard-next="1">← Back</button><button>Create account</button></fieldset></form>')
