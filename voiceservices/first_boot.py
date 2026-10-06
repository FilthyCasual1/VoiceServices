"""One-time, HTTPS-only appliance ownership wizard."""
import html,json,secrets
from . import login_protection,regional
E=lambda v:html.escape(str(v),quote=True)
def pending(app):
    if not app.config.get('first_boot_setup'):return False
    with app.store.connect() as db:return db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone() is None

def page(app,env,data,cookie,method,send):
    if not pending(app):return send('303 See Other','',extra=[('Location','/login')])
    if not app.secure or not app.base.startswith('https://') or not app.store.accounts:return send('503 Service Unavailable','First-boot setup requires HTTPS and the local account provider.')
    nonce=cookie['vs_setup'].value if 'vs_setup' in cookie else '';error=''
    if method=='POST':
        wait=login_protection.reserve(app,env,'login')
        if wait:return send('429 Too Many Requests','Please wait before retrying setup.',extra=[('Retry-After',str(wait))])
        try:
            if not nonce or not secrets.compare_digest(nonce,data.get('csrf','')):raise ValueError('Your setup form expired. Please try again.')
            if data.get('password')!=data.get('confirm_password'):raise ValueError('Passwords do not match.')
            payload={'password':data.get('password',''),'title':data.get('title',''),'timezone':data.get('timezone','UTC')}
            app.store.accounts.call('setup-complete',data.get('username',''),data.get('setup_code',''),json.dumps(payload))
            return send('200 OK',app.page('Setup complete','<div class="signin-card"><div class="signin-banner"><strong>Your portal is ready</strong><small>Your local administrator account has been created.</small></div><div class="panel"><p>Sign in to choose your addons and complete your host settings.</p><a class="button" href="/login">Sign in</a></div></div>',None),extra=[('Set-Cookie','vs_setup=; HttpOnly; Secure; SameSite=Strict; Path=/setup; Max-Age=0')])
        except ValueError as exc:
            login_protection.failed(env,'login',app);error='<p class="notice error">'+E(exc)+'</p>'
    nonce=secrets.token_urlsafe(32)
    form=error+'''<div class="signin-card firstboot-card"><div class="signin-banner"><strong>Welcome to ServiceReady</strong><small>Let’s set up your INSAP appliance.</small></div><form method="post" class="panel" data-firstboot-wizard><input type="hidden" name="csrf" value="'''+E(nonce)+'''"><ol class="tools-steps"><li>Welcome</li><li>Administrator</li><li>Review</li></ol>
<fieldset data-firstboot-step="0"><legend>1. Claim this appliance</legend><p>The portal follows the address assigned by DHCP, including after a restart. Enter the unique setup code shown on the VM console to claim it.</p><label>Setup code</label><input name="setup_code" autocomplete="off" required><button type="button" data-firstboot-next="1">Next →</button></fieldset>
<fieldset data-firstboot-step="1"><legend>2. Administrator and portal</legend><label>Administrator username</label><input name="username" autocomplete="username" pattern="[a-z_][a-z0-9_-]{2,31}" required><label>Password (12 or more characters)</label><input type="password" name="password" autocomplete="new-password" minlength="12" maxlength="1024" required><p>If the Linux root console has a blank password, this password secures it too. Existing root passwords are retained.</p><label>Confirm password</label><input type="password" name="confirm_password" autocomplete="new-password" required><label>Portal title</label><input name="title" value="ServiceReady" maxlength="100" required><label>Portal time zone</label>'''+regional.timezone_select('timezone','UTC')+'''<footer><button type="button" data-firstboot-next="0">← Back</button><button type="button" data-firstboot-next="2">Next →</button></footer></fieldset>
<fieldset data-firstboot-step="2"><legend>3. Ready to finish</legend><p data-firstboot-review>A local operating-system administrator will be created. Setup will close after this account is saved. Addons remain optional so the appliance stays small.</p><p>You can configure storage, identity providers and addons after signing in. Network settings remain under OpenWrt control.</p><footer><button type="button" data-firstboot-next="1">← Back</button><button type="submit">Finish setup</button></footer></fieldset></form></div>'''
    return send('200 OK',app.page('Set up your portal',form,None),extra=[('Set-Cookie',f'vs_setup={nonce}; HttpOnly; Secure; SameSite=Strict; Path=/setup; Max-Age=900')])
