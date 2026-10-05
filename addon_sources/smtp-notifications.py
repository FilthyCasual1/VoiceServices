"""Optional receive-only SMTP notification gateway."""
import html,ipaddress,json,ssl,time
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
E=lambda v:html.escape(str(v),quote=True)
DEFAULT={'enabled':False,'host':'127.0.0.1','port':2525,'allowed':'127.0.0.1/32','routes':''}
def settings(app):
    with app.store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS addon_status(id TEXT PRIMARY KEY,status TEXT,at INTEGER)')
        row=db.execute("SELECT settings FROM addons WHERE id='smtp-notifications'").fetchone()
    return dict(DEFAULT,**(json.loads(row[0]) if row else {}))
def routes(app,s):
    result={}
    with app.store.connect() as db: users={r['username']:r['id'] for r in db.execute('SELECT id,username FROM users')}
    for line in s['routes'].splitlines():
        if not line.strip(): continue
        parts=[p.strip() for p in line.split('|')]
        if len(parts)!=2: raise ValueError('Use one route per line: receiving-address | portal-username.')
        address,username=parts
        for email in (address,):
            if email and (parseaddr(email)[1]!=email or '@' not in email or any(c.isspace() for c in email)): raise ValueError('Use plain email addresses in routes.')
        if not address or address.lower() in result or username not in users: raise ValueError('Check recipient routes and portal usernames.')
        result[address.lower()]={'user_id':users[username]}
    return result

def admin_change(app,data,services):
    s=settings(app)
    for key in ('host','allowed','routes'): s[key]=data.get(key,s[key]).strip()
    s['enabled']=data.get('enabled')=='yes'
    try:
        s['port']=int(data.get('port',s['port']));ipaddress.ip_address(s['host'])
        networks=[ipaddress.ip_network(x.strip(),strict=False) for x in s['allowed'].split(',')]
    except ValueError: raise ValueError('Enter a bind IP, trusted source CIDRs, and a valid port.')
    if not networks or not 1<=s['port']<=65535: raise ValueError('Check port and source networks.')
    configured=routes(app,s)
    if s['enabled'] and not configured: raise ValueError('Add at least one recipient route before enabling SMTP.')
    with app.store.connect() as db: db.execute("INSERT OR REPLACE INTO addons VALUES('smtp-notifications',?)",(json.dumps(s),))
    return 'SMTP settings saved. The worker applies changes automatically.'
def admin_render(app,user,services):
    s=settings(app)
    with app.store.connect() as db: state=db.execute("SELECT status,at FROM addon_status WHERE id='smtp-notifications'").fetchone()
    status=state['status'] if state and state['at']>time.time()-10 else 'Worker unavailable or not started'
    text='<p class="notice">'+E(status)+'</p><p>Receive application emails as portal inbox notifications. Only trusted source IPs and explicitly mapped recipients are accepted.</p><div class="panel"><form method="post"><input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
    for key,label in [('host','Listen IP'),('port','SMTP port'),('allowed','Trusted application networks (comma-separated CIDRs)')]:
        text+='<label>'+label+'</label><input name="'+key+'" value="'+E(s[key])+'">'
    text+='<label>Recipient routes</label><textarea name="routes" rows="6">'+E(s['routes'])+'</textarea><p>One per line: receiving-address | portal-username.</p><label>SMTP listener</label><select name="enabled"><option value="no">Disabled</option><option value="yes"'+(' selected' if s['enabled'] else '')+'>Enabled</option></select><br><button>Save SMTP settings</button></form></div><p>Incoming SMTP uses trusted source IPs without SMTP AUTH. Optional STARTTLS uses smtp_tls_cert and smtp_tls_key paths in the host configuration.</p><p>Priority: X-Priority 1–2 or Importance high → Urgent; X-Priority 3 → Caution; other messages → Info. Inbox notices display plain text; attachments are not stored.</p>'
    return text

class Gateway:
    def __init__(self,app,s): self.app=app;self.s=s;self.ready=True
    def trusted(self,session):
        try: return self.ready and self.app.modules.installed('smtp-notifications') and any(ipaddress.ip_address(session.peer[0]) in ipaddress.ip_network(x.strip(),strict=False) for x in self.s['allowed'].split(','))
        except ValueError: return False
    async def handle_MAIL(self,server,session,envelope,address,mail_options):
        if not self.trusted(session): return '550 Source not authorized'
        envelope.mail_from=address;envelope.mail_options.extend(mail_options);return '250 OK'
    async def handle_RCPT(self,server,session,envelope,address,rcpt_options):
        if not self.trusted(session): return '550 Source not authorized'
        if len(envelope.rcpt_tos)>=50: return '452 Too many recipients'
        if address.lower() not in routes(self.app,self.s): return '550 Recipient not configured'
        envelope.rcpt_tos.append(address);return '250 OK'
    async def handle_DATA(self,server,session,envelope):
        if not self.trusted(session): return '550 Source not authorized'
        raw=envelope.original_content
        if len(raw)>1024*1024: return '552 Message too large'
        mapped=routes(self.app,self.s)
        if any(r.lower() not in mapped for r in envelope.rcpt_tos): return '550 Recipient no longer configured'
        msg=BytesParser(policy=policy.default).parsebytes(raw)
        try: part=msg.get_body(preferencelist=('plain',));body=part.get_content() if part else 'No plain-text body was included. HTML and attachments are not displayed in the inbox.'
        except (LookupError,UnicodeError): body='Message body could not be decoded.'
        priority='urgent' if str(msg.get('X-Priority',''))[:1] in ('1','2') or str(msg.get('Importance','')).lower()=='high' else 'caution' if str(msg.get('X-Priority',''))[:1]=='3' else 'info'
        destinations=[mapped[r.lower()] for r in envelope.rcpt_tos]
        with self.app.store.connect() as db:
            for uid in {r['user_id'] for r in destinations if r['user_id'] is not None}:
                db.execute('INSERT INTO notifications(user_id,title,body,created,sender,priority) VALUES(?,?,?,?,?,?)',(uid,str(msg.get('Subject','Application notification'))[:120],str(body)[:5000],int(time.time()),('SMTP: '+envelope.mail_from)[:160],priority))
        return '250 Notification accepted'

def worker_main():
    import argparse
    from voiceservices.web import App
    from aiosmtpd.controller import Controller
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);args=parser.parse_args()
    with open(args.config) as f: app=App(json.load(f))
    controller=None;previous=None;dropped=False
    try:
        while app.modules.installed('smtp-notifications'):
            s=settings(app)
            if s!=previous:
                if controller: controller.stop();controller=None
                if dropped and s['port']<1024: return
                previous=s
                if s['enabled']:
                    context=None
                    if app.config.get('smtp_tls_cert'):
                        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(app.config['smtp_tls_cert'],app.config['smtp_tls_key'])
                    gateway=Gateway(app,s);gateway.ready=False
                    controller=Controller(gateway,hostname=s['host'],port=s['port'],data_size_limit=1024*1024,enable_SMTPUTF8=False,tls_context=context)
                    controller.start()
                    import os
                    if hasattr(os,'getuid') and os.getuid()==0:
                        import pwd,grp
                        os.setgroups([]);os.setgid(grp.getgrnam('serviceready').gr_gid);os.setuid(pwd.getpwnam('serviceready').pw_uid);dropped=True
                    gateway.ready=True
            with app.store.connect() as db: db.execute("INSERT OR REPLACE INTO addon_status VALUES('smtp-notifications',?,?)",('Running' if controller else 'Disabled',int(time.time())))
            time.sleep(.5)
    finally:
        if controller: controller.stop()
