import html,json,time
from urllib.parse import urlencode,urlsplit
E=lambda value:html.escape(str(value),quote=True)
import types
from voiceservices.core import calculate
phone=types.ModuleType("phone")
exec('"""Cisco XML rendering, independent of CUCM provisioning and CTI."""\nfrom urllib.parse import urlencode\nfrom xml.etree.ElementTree import Element, SubElement, tostring\n\n\ndef field(parent, name, value):\n    SubElement(parent, name).text = str(value)\n\n\ndef xml(root):\n    return tostring(root, encoding=\'utf-8\', xml_declaration=True)\n\n\ndef text(title, message):\n    root = Element(\'CiscoIPPhoneText\')\n    field(root, \'Title\', title)\n    field(root, \'Prompt\', \'ServiceReady\')\n    field(root, \'Text\', message)\n    return xml(root)\n\n\ndef menu(base, token, plugins=None):\n    root = Element(\'CiscoIPPhoneMenu\')\n    field(root, \'Title\', \'ServiceReady\')\n    field(root, \'Prompt\', \'Select an application\')\n    entries = [(\'Directory\',\'directory\'), (\'Recordings\',\'recordings\'), (\'Network status\',\'network\'), (\'Save current number\',\'current-number\')]\n    if plugins is None:\n        entries.insert(1, (\'Calculator\',\'calculator\'))\n    else:\n        entries[1:1] = [(p[\'package\'][\'name\'],\'plugin/\'+p[\'id\']) for p in plugins if p[\'enabled\']]\n    for label, route in entries:\n        item = SubElement(root, \'MenuItem\')\n        field(item, \'Name\', label)\n        field(item, \'URL\', base+\'/phone/\'+route+\'?\'+urlencode({\'token\':token}))\n    return xml(root)\n\n\ndef calculator(base, token):\n    root = Element(\'CiscoIPPhoneInput\')\n    field(root, \'Title\', \'Calculator\')\n    field(root, \'Prompt\', \'Operation: add/subtract/multiply/divide\')\n    field(root, \'URL\', base+\'/phone/calculate?\'+urlencode({\'token\':token}))\n    for label, param, default, flags in [(\'First number\',\'left\',\'0\',\'A\'),\n                                        (\'Operation\',\'operation\',\'add\',\'A\'),\n                                        (\'Second number\',\'right\',\'0\',\'A\')]:\n        item = SubElement(root, \'InputItem\')\n        for tag, value in [(\'DisplayName\',label), (\'QueryStringParam\',param),\n                           (\'DefaultValue\',default), (\'InputFlags\',flags)]:\n            field(item, tag, value)\n    return xml(root)\n\n\ndef directory(contacts):\n    root = Element(\'CiscoIPPhoneDirectory\')\n    field(root, \'Title\', \'Directory\')\n    field(root, \'Prompt\', \'Select a contact to dial\')\n    for contact in contacts:\n        item = SubElement(root, \'DirectoryEntry\')\n        field(item, \'Name\', contact[\'name\'])\n        field(item, \'Telephone\', contact[\'number\'])\n    return xml(root)\n',phone.__dict__)
"""Installable declarative phone plugins; packages cannot execute server code."""
import json
import re


class Plugins:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS plugins(id TEXT PRIMARY KEY, manifest TEXT NOT NULL, settings TEXT NOT NULL, enabled INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS plugin_metadata(key TEXT PRIMARY KEY)')
            if db.execute("SELECT 1 FROM plugin_metadata WHERE key='seeded'").fetchone(): return
            db.execute("INSERT INTO plugin_metadata VALUES('seeded')")
            db.execute('INSERT OR IGNORE INTO plugins VALUES(?,?,?,1)', ('calculator', json.dumps({'id':'calculator','name':'Calculator','version':'1.0','kind':'calculator','description':'Arithmetic on the telephone display.','fields':{}}), '{}'))

    def list(self):
        with self.store.connect() as db:
            return [dict(row, package=json.loads(row['manifest']), config=json.loads(row['settings'])) for row in db.execute('SELECT * FROM plugins ORDER BY id')]

    def install(self, raw):
        try: package = json.loads(raw)
        except (ValueError, TypeError): raise ValueError('Package must be valid JSON.')
        if not isinstance(package, dict): raise ValueError('Package must be an object.')
        for key in ('id','name','version','kind'):
            if not isinstance(package.get(key), str) or not 1 <= len(package[key]) <= 80: raise ValueError('Package requires id, name, version and kind.')
        if not re.fullmatch('[a-z][a-z0-9-]{0,39}', package['id']): raise ValueError('Invalid plugin ID.')
        if package['kind'] != 'text': raise ValueError('Uploaded plugins must use the text renderer.')
        fields = package.get('fields', {})
        if not isinstance(fields, dict) or len(fields)>12: raise ValueError('Maximum twelve configuration fields.')
        for key, label in fields.items():
            if not isinstance(key,str) or not re.fullmatch('[a-z][a-z0-9_]{0,30}',key) or not isinstance(label,str) or len(label)>80: raise ValueError('Invalid configuration field.')
        if not isinstance(package.get('text'),str) or len(package['text'])>4000: raise ValueError('Plugin requires phone text (maximum 4000 characters).')
        if len(str(package.get('description','')))>500: raise ValueError('Description too long.')
        placeholders = re.findall(r'\{([^{}]+)\}', package['text'])
        if any(key not in fields for key in placeholders): raise ValueError('Text placeholders must name configuration fields.')
        with self.store.connect() as db:
            if db.execute('SELECT 1 FROM plugins WHERE id=?',(package['id'],)).fetchone(): raise ValueError('Plugin ID already installed. Remove it before installing a replacement.')
            db.execute('INSERT INTO plugins VALUES(?,?,?,1)',(package['id'],json.dumps(package),'{}'))

    def change(self, plugin_id, data):
        item = next((p for p in self.list() if p['id']==plugin_id),None)
        if not item: raise ValueError('Plugin not found.')
        with self.store.connect() as db:
            if data.get('action')=='remove': db.execute('DELETE FROM plugins WHERE id=?',(plugin_id,))
            else:
                config = {key:data.get('config_'+key,'')[:500] for key in item['package'].get('fields',{})}
                db.execute('UPDATE plugins SET settings=?,enabled=? WHERE id=?',(json.dumps(config),int(data.get('enabled')=='yes'),plugin_id))

    def render(self, plugin_id, base, token):
        item = next((p for p in self.list() if p['id']==plugin_id and p['enabled']),None)
        if not item: return None
        package = item['package']
        if package['kind']=='calculator': return phone.calculator(base,token)
        message = re.sub(r'\{([^{}]+)\}',lambda match:item['config'].get(match[1],''),package['text'])
        return phone.text(package['name'],message)

APPS = {'calculator':'Calculator', 'rss':'RSS Reader', 'weather':'Weather', 'flights':'Flight Tracker',
        'network':'Network Management', 'recordings':'Call Recordings'}

def phone_request(self,path,method,data,send):
    if path.startswith('/phone/'):
        if method != 'GET': return send('405 Method Not Allowed','GET required.')
        token = data.get('token','')
        user = self.store.phone_user(token)
        if not user:
            return send('403 Forbidden',phone.text('Sign in required','Bind this terminal from My Phone. Native phone roaming synchronization is not connected.'),'text/xml; charset=utf-8')
        route = path.removeprefix('/phone/')
        if route == 'services': content = phone.menu(self.base,token, self.plugins.list())
        elif route.startswith('plugin/'):
            content = self.plugins.render(route[7:],self.base,token)
            if content is None: return send('404 Not Found',phone.text('Not found','Plugin unavailable.'),'text/xml; charset=utf-8')
        elif route == 'directory': content = phone.directory(self.store.contacts(user['id'],data.get('q',''))[:32])
        elif route == 'calculator': content = phone.calculator(self.base,token)
        elif route == 'calculate':
            try: result = calculate(data.get('left',''),data.get('operation',''),data.get('right',''))
            except ValueError as exc: result = str(exc)
            content = phone.text('Calculator',result)
        elif route == 'current-number':
            content = phone.text('Save current number','the phone system CTI adapter is not connected. No call number has been captured.')
        elif route in APPS:
            content = phone.text(APPS[route], 'Integration not connected. Configure and implement the provider in the web console.')
        else: return send('404 Not Found',phone.text('Not found','Unknown service.'),'text/xml; charset=utf-8')
        return send('200 OK',content,'text/xml; charset=utf-8')

def page(self,path,method,data,user,env,send):
    note = ''
    try:
        if path == '/applications' and method == 'POST':
            if user['role'] != 'admin': raise PermissionError('Administrator access required to manage plugins.')
            if data.get('action') == 'install': self.plugins.install(data.get('manifest',''))
            else: self.plugins.change(data.get('plugin',''),data)
            return send('303 See Other','',extra=[('Location','/applications')])
        if path == '/directory' and method == 'POST':
            self.store.add_contact(user,data.get('name',''),data.get('number',''),data.get('scope')=='shared')
            return send('303 See Other','',extra=[('Location','/directory')])
        if method == 'POST' and (path == '/preferences' or (path == '/my-phone' and data.get('action') == 'preferences')):
            values = {k:data.get(k,'')[:200] for k in ('weather_location','rss_url','flight','widget')}
            if values['widget'] not in ('network','weather','off'): raise ValueError('Invalid widget selection.')
            self.store.preferences(user['id'],values)
            return send('303 See Other','',extra=[('Location','/my-phone#settings')])
        if path == '/my-phone' and method == 'POST':
            if data.get('action') == 'unbind':
                self.store.unbind_phone(user['id'])
                note = '<p class="notice">Application terminal signed out. Native phone login is unchanged.</p>'
            else:
                binding = self.store.bind_phone(user,data.get('device','').upper())
                url = self.base+'/phone/services?'+urlencode({'token':binding})
                note = '<p class="notice">Application binding created for eight hours. Previous binding revoked.<br>Private Services URL: <code>'+E(url)+'</code></p>'
    except PermissionError as exc:
        return send('403 Forbidden',self.page('Access denied',E(exc),user))
    except ValueError as exc:
        return send('400 Bad Request',self.page('Check your input','<p class="notice error">'+E(exc)+'</p>',user))
    guest=user["role"]=="guest"
    csrf='<input type="hidden" name="csrf" value="'+E(user["csrf"])+'">'
    if path == '/self-care':
        title = 'Self Care'
        url=self.config.get('services',{}).get('self_care','')
        access='<a href="'+E(url)+'" target="_blank" rel="noopener noreferrer">Open Self Care</a>' if self.valid_link(url) else 'Not configured'
        content='<div class="panel">'+access+'</div><h2>Line keys and speed dials</h2><div class="panel">Use Self Care to edit supported speed-dial numbers and labels. Available buttons depend on the phone model and its assigned button template. Extension and line assignments require managed phone system configuration; the custom editor is not connected yet.</div>'
    elif path == '/directory':
        title = 'Directory'
        rows = ''.join('<tr><td>'+E(c['name'])+'</td><td>'+E(c['number'])+'</td><td>'+('Shared' if c['owner'] is None else 'Personal')+'</td></tr>' for c in self.store.contacts(user['id'],data.get('q','')))
        scope = '<option value="shared">Shared</option>' if user['role']=='admin' else ''
        content = '<form method="get"><input name="q" placeholder="Search contacts" value="'+E(data.get('q',''))+'"><button>Search</button></form><table><tr><th>Name</th><th>Number</th><th>Directory</th></tr>'+rows+'</table><h2>Add contact</h2><div class="panel"><form method="post">'+csrf+'<label>Name</label><input name="name" maxlength="100" required><label>Number / dial string</label><input name="number" maxlength="40" required><label>Directory</label><select name="scope"><option value="personal">Personal</option>'+scope+'</select><br><button>Save contact</button></form></div><p class="muted">Save current call requires the the phone system CTI adapter; manual entry works now.</p>'
    elif path == '/preferences':
        title = 'Application preferences'
        prefs = json.loads(user['preferences'])
        fields = ''.join('<label>'+label+'</label><input name="'+key+'" maxlength="200" value="'+E(prefs.get(key,''))+'">' for key,label in [('weather_location','Weather location'),('rss_url','RSS feed URL'),('flight','Tracked flight')])
        options = ''.join('<option value="'+v+'"'+(' selected' if prefs.get('widget','network')==v else '')+'>'+label+'</option>' for v,label in [('network','Network status'),('weather','Weather'),('off','Disabled')])
        content = '<p class="notice">Preferences belong to your user account and follow application terminal bindings. External providers are not connected.</p><div class="panel"><form method="post" action="/my-phone">'+csrf+'<input type="hidden" name="action" value="preferences">'+fields+'<label>Status widget</label><select name="widget">'+options+'</select><br><button>Save preferences</button></form></div>'
    elif path == '/register-phone':
        title = 'Set up a phone'
        settings = self.config.get('self_provisioning', {})
        rows = [('TFTP server', self.config.get('tftp_host') or 'Not configured'),
                ('Self-provisioning IVR number', settings.get('ivr_number') or 'Not configured'),
                ('Phone network / VLAN', settings.get('network') or 'Ask your administrator')]
        content = '<p class="notice">the phone system performs registration using its universal device and line templates. This portal supplies setup details; it does not create a separate registration request.</p><h2>Connection details</h2><table>'+''.join('<tr><th>'+E(k)+'</th><td>'+E(v)+'</td></tr>' for k,v in rows)+'</table>'
        content += '<h2>Register your phone</h2><div class="panel"><ol><li>Connect the phone to the designated phone network.</li><li>Obtain the configured TFTP server through DHCP, or enter the server above if your deployment requires manual setup.</li><li>Wait for the phone system auto-registration and a temporary extension.</li><li>Use the native self-provisioning screen if configured for this handset, or dial the self-provisioning IVR number above.</li><li>Provide the phone system identification and authentication details requested by the native workflow. the phone system applies the assigned templates and extension.</li></ol></div>'
        if guest:
            content += '<p><a href="/login">Sign in to view your personal the phone system setup details.</a></p>'
        else:
            identity = settings.get('users', {}).get(user['username'], {})
            content += '<h2>Your phone identity</h2><table>'+''.join('<tr><th>'+E(k)+'</th><td>'+E(v)+'</td></tr>' for k,v in [('Phone user ID', identity.get('user_id') or 'Not linked'), ('Self-service user ID', identity.get('self_service_id') or 'Not linked'), ('Primary extension', identity.get('extension') or 'Not linked')])+'</table><p class="muted">These details are administrator-configured mappings, not live the phone system verification. Enter your PIN only in the native phone workflow. The portal does not store or display it.</p>'
        content += '<p class="muted">the phone system must have auto-registration, templates, an eligible user profile, and the relevant self-provisioning services configured. Native phone login support must be checked for each handset model. Self-provisioning assigns a phone; phone roaming handles later roaming logins.</p>'
    elif path == '/my-phone':
        title = 'My Phone'
        content = note+'<p class="notice">Manual application binding only. This does not configure the phone system, verify handset ownership, or perform native phone roaming. Anyone possessing the generated URL can read this application directory; protect it like a password. Phone login synchronization will replace this development mechanism.</p><div class="panel"><form method="post">'+csrf+'<label>Device name</label><input name="device" placeholder="SEP001122AABBCC" required><br><button>Bind application terminal</button></form><form method="post">'+csrf+'<input type="hidden" name="action" value="unbind"><button>Sign out application terminal</button></form></div>'
    elif path == '/applications':
        title = 'Applications'
        content = '<p class="notice">Install separate phone plugins and configure their settings here. Applications appear on the telephone Services menu; they run on the phone display.</p><h2>Installed plugins</h2><table><tr><th>Application / package</th><th>Version</th><th>Status</th><th>Description</th></tr>'
        for item in self.plugins.list():
            package = item['package']
            content += '<tr><td><a href="#plugin-'+E(item['id'])+'">'+E(package['name'])+'</a><br><small>'+E(item['id'])+'</small></td><td>'+E(package['version'])+'</td><td>'+('Enabled' if item['enabled'] else 'Disabled')+'</td><td>'+E(package.get('description',''))+'</td></tr>'
        content += '</table>'
        if user['role'] == 'admin':
            for item in self.plugins.list():
                package = item['package']
                fields = ''.join('<label>'+E(label)+'</label><input name="config_'+E(key)+'" maxlength="500" value="'+E(item['config'].get(key,''))+'">' for key,label in package.get('fields',{}).items())
                content += '<h2 id="plugin-'+E(item['id'])+'">'+E(package['name'])+' — Configuration</h2><div class="panel"><form method="post">'+csrf+'<input type="hidden" name="plugin" value="'+E(item['id'])+'">'+fields+'<label>Services menu</label><select name="enabled"><option value="yes"'+(' selected' if item['enabled'] else '')+'>Enabled</option><option value="no"'+(' selected' if not item['enabled'] else '')+'>Disabled</option></select><br><button name="action" value="save">Save settings</button><button name="action" value="remove">Remove plugin</button></form></div>'
            content += '<h2>Install a plugin</h2><div class="panel"><form method="post">'+csrf+'<input type="hidden" name="action" value="install"><label for="manifest">Plugin package (.json contents)</label><textarea id="manifest" name="manifest" rows="12" required spellcheck="false" placeholder="Paste a ServiceReady plugin manifest"></textarea><br><button>Install plugin</button></form><p class="muted">Declarative text plugins support configurable phone screens. Packages cannot execute server code. Provider adapters for RSS, weather and flights are still pending.</p></div>'
        else:
            content += '<p><a href="/login">Sign in with an administrator account to install and configure plugins.</a></p>'
        content += '<p><a href="/my-phone#settings">Personal phone preferences</a></p>'
    elif path == '/recordings':
        title='Call Recordings';content='<p class="notice">Adapter not connected. No recordings are available.</p>'
    else: return None
    if guest and path == '/directory':
        content = content[:content.index('<h2>Add contact</h2>')]+'<p><a href="/login">Sign in to add or edit contacts and view your personal directory.</a></p>'
    if guest and path == '/preferences':
        content = '<p class="notice">Phone application preferences follow your user identity.</p><p><a href="/login">Sign in to edit your preferences.</a></p>'
    if path == '/my-phone':
        binding_content = content if not guest else '<p><a href="/login">Sign in to manage your phone and personal settings.</a></p>'
        sections = []
        for route, anchor, heading in [('/register-phone','setup','Phone setup'),('/self-care','customization','Line keys and customization'),('/preferences','settings','Phone application settings')]:
            section_env = dict(env, PATH_INFO=route, REQUEST_METHOD='GET', QUERY_STRING='', CONTENT_LENGTH='0')
            section_env['voiceservices.section'] = True
            body = b''.join(self(section_env, lambda status, headers: None)).decode()
            fragment = body.split('</h1>', 1)[1].split('</main>', 1)[0]
            sections.append('<section id="'+anchor+'"><h2>'+heading+'</h2>'+fragment+'</section>')
        content = ''.join(sections)+'<h2>Application terminal binding</h2>'+binding_content
    return send('200 OK',self.page(title,content,user))


def resource(app,name): return Plugins(app.store)

# Linked phone-system account: administrator-controlled mapping, read-only AXL lookup.
import base64,os,ssl
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from xml.etree import ElementTree as ET

def identity_tables(app):
    with app.store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS voice_user_links(user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,userid TEXT NOT NULL UNIQUE,profile TEXT NOT NULL DEFAULT \'{}\',refreshed INTEGER NOT NULL DEFAULT 0)')
def axl_endpoint(app):
    return app.config.get('voice_axl_url','')
def axl_request(app,method,body):
    endpoint=axl_endpoint(app);parsed=urlsplit(endpoint)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path!='/axl/' or parsed.query or parsed.fragment: raise ValueError('Administrator must configure a valid HTTPS AXL endpoint.')
    username=os.environ.get('SERVICEREADY_AXL_USERNAME','');password=os.environ.get('SERVICEREADY_AXL_PASSWORD','')
    if not username or not password: raise ValueError('AXL service credentials are not configured on the portal server.')
    if method not in ('getUser','addUser'): raise ValueError('Unsupported AXL operation.')
    envelope=('<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:axl="http://www.cisco.com/AXL/API/12.5"><soapenv:Body><axl:'+method+'>'+body+'</axl:'+method+'></soapenv:Body></soapenv:Envelope>').encode()
    auth=base64.b64encode((username+':'+password).encode()).decode()
    request=Request(endpoint,data=envelope,headers={'Content-Type':'text/xml; charset=utf-8','SOAPAction':'"CUCM:DB ver=12.5 '+method+'"','Authorization':'Basic '+auth})
    try:
        context=ssl.create_default_context(cafile=app.config.get('voice_axl_ca_file') or None)
        with urlopen(request,context=context,timeout=15) as response: raw=response.read(2*1024**2+1)
        if len(raw)>2*1024**2 or b'<!DOCTYPE' in raw or b'<!ENTITY' in raw: raise ValueError('Invalid AXL response.')
        tree=ET.fromstring(raw)
        if any(element.tag.rsplit('}',1)[-1]=='Fault' for element in tree.iter()): raise ValueError('Phone system rejected the AXL operation.')
        return tree
    except (HTTPError,URLError,OSError,ET.ParseError) as exc: raise ValueError('AXL operation failed. Check certificate, service credentials, permissions and user ID. A timed-out create may have succeeded; check CUCM before retrying.') from exc

def axl_user(app,identifier):
    tree=axl_request(app,'getUser','<userid>'+E(identifier)+'</userid><returnedTags><userid/><firstName/><lastName/><mailid/><telephoneNumber/><primaryExtension/><associatedDevices/></returnedTags>')
    found=next((e for e in tree.iter() if e.tag.rsplit('}',1)[-1]=='user'),None)
    if found is None: raise ValueError('Linked user was not returned by the phone system.')
    data={e.tag.rsplit('}',1)[-1]:(e.text or '') for e in found if e.tag.rsplit('}',1)[-1] in ('userid','firstName','lastName','mailid','telephoneNumber')}
    extension=next((e.text for e in found.iter() if e.tag.rsplit('}',1)[-1]=='pattern'),None)
    data['extension']=extension or '';data['devices']=', '.join(e.text or '' for e in found.iter() if e.tag.rsplit('}',1)[-1]=='device')
    if data.get('userid')!=identifier: raise ValueError('Phone-system response did not match the linked identity.')
    return data

def account_refresh(app,user):
    identity_tables(app)
    with app.store.connect() as db: row=db.execute('SELECT userid FROM voice_user_links WHERE user_id=?',(user['id'],)).fetchone()
    if not row: raise ValueError('Ask an administrator to link your phone-system account first.')
    value=axl_user(app,row['userid'])
    with app.store.connect() as db: db.execute('UPDATE voice_user_links SET profile=?,refreshed=? WHERE user_id=?',(json.dumps(value),int(time.time()),user['id']))
    return 'Linked phone-system profile refreshed. Portal credentials are separate.'
def account_panel(app,user):
    identity_tables(app)
    with app.store.connect() as db: row=db.execute('SELECT * FROM voice_user_links WHERE user_id=?',(user['id'],)).fetchone()
    if not row: return '<h3>Phone-system account</h3><p>No linked identity. Ask your administrator to map your account.</p>'
    value=json.loads(row['profile']);csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
    rows=[('Linked user ID',row['userid']),('Profile status','Cached lookup; refreshed '+time.strftime('%Y-%m-%d %H:%M UTC',time.gmtime(row['refreshed'])) if row['refreshed'] else 'Not yet verified'),('Name',value.get('firstName','')+' '+value.get('lastName','')),('Email',value.get('mailid','')),('Telephone',value.get('telephoneNumber','')),('Primary extension',value.get('extension','')),('Devices',value.get('devices',''))]
    return '<h3>Phone-system account</h3><table>'+''.join('<tr><th>'+E(k)+'</th><td>'+E(v)+'</td></tr>' for k,v in rows)+'</table><form method="post">'+csrf+'<button name="action" value="voice-refresh">Refresh linked profile</button></form><p>Read-only CUCM profile lookup. Portal password changes do not change your phone-system password or PIN.</p>'
def admin_change(app,data,services):
    identity_tables(app)
    if data.get('action')=='axl-settings':
        endpoint=data.get('endpoint','').strip();parsed=urlsplit(endpoint)
        if endpoint and (parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path!='/axl/' or parsed.query or parsed.fragment): raise ValueError('Use an HTTPS endpoint ending in /axl/.')
        values={'voice_axl_url':endpoint,'voice_axl_ca_file':data.get('ca_file','').strip()}
        with app.store.connect() as db:
            for key,value in values.items(): db.execute('INSERT OR REPLACE INTO portal_settings VALUES(?,?)',(key,json.dumps(value)))
        app.config.update(values);return 'AXL endpoint saved. Configure service credentials in the server environment.'
    name=data.get('username','').strip();identifier=data.get('userid','').strip()
    with app.store.connect() as db:
        user=db.execute('SELECT id FROM users WHERE username=?',(name,)).fetchone()
        if not user: raise ValueError('Select an existing portal username.')
        if data.get('action')=='unlink': db.execute('DELETE FROM voice_user_links WHERE user_id=?',(user['id'],));return 'Phone identity unlinked.'
        if not identifier or len(identifier)>128: raise ValueError('Enter a phone-system user ID.')
        other=db.execute('SELECT user_id FROM voice_user_links WHERE userid=?',(identifier,)).fetchone()
        if other and other['user_id']!=user['id']: raise ValueError('That phone identity is already linked to another portal user.')
        if data.get('action')=='create-cucm':
            if data.get('confirm')!='yes': raise ValueError('Confirm creation of a CUCM user.')
            password=data.get('cucm_password','');pin=data.get('cucm_pin','');last=data.get('last_name','').strip();first=data.get('first_name','').strip()
            if not last or len(last)>100 or len(first)>100 or not 12<=len(password)<=1024 or (pin and not re.fullmatch('[0-9]{4,20}',pin)): raise ValueError('Enter a last name, a CUCM password of 12–1024 characters, and an optional numeric PIN of 4–20 digits.')
            body='<user><firstName>'+E(first)+'</firstName><lastName>'+E(last)+'</lastName><userid>'+E(identifier)+'</userid><password>'+E(password)+'</password>'
            if pin: body+='<pin>'+E(pin)+'</pin>'
            body+='<associatedGroups><userGroup><name>Standard CCM End Users</name></userGroup></associatedGroups></user>'
            tree=axl_request(app,'addUser',body)
            if not any(e.tag.rsplit('}',1)[-1]=='return' and e.text for e in tree.iter()): raise ValueError('CUCM creation result could not be verified. Check the remote user before retrying.')
        try: db.execute("INSERT INTO voice_user_links(user_id,userid) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET userid=excluded.userid,profile='{}',refreshed=0",(user['id'],identifier))
        except Exception as exc: raise ValueError('Identity could not be linked.') from exc
    return 'CUCM user created and linked. Refresh My Account to retrieve its profile.' if data.get('action')=='create-cucm' else 'Phone identity linked; refresh it from My Account to verify.'
def admin_render(app,user,services):
    csrf='<input type="hidden" name="csrf" value="'+E(user["csrf"])+'">'
    content=''
    content+='</table><div class="panel"><form method="post">'+csrf+'<input type="hidden" name="action" value="axl-settings"><label>AXL HTTPS endpoint</label><input name="endpoint" type="url" value="'+E(axl_endpoint(app))+'"><label>Trusted CA file on portal server (optional)</label><input name="ca_file" value="'+E(app.config.get("voice_axl_ca_file",""))+'"><br><button>Save AXL settings</button></form><p>AXL service credentials are configured on the server. TLS certificate validation is required.</p></div>'
    return content

def account_links_render(app,user):
    identity_tables(app);csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
    content='<p>Link portal users to their phone-system account. Live lookup uses the configured AXL endpoint and server-side service credentials; passwords and PINs remain separate.</p><table><tr><th>Portal user</th><th>Phone user ID</th></tr>'
    with app.store.connect() as db:
        for row in db.execute('SELECT username,userid FROM voice_user_links JOIN users ON users.id=voice_user_links.user_id'): content+='<tr><td>'+E(row['username'])+'</td><td>'+E(row['userid'])+'</td></tr>'
    return content+'<div class="panel"><form method="post">'+csrf+'<label>Portal username</label><input name="username" required><label>Phone-system user ID</label><input name="userid"><br><button name="action" value="link">Link identity</button><button name="action" value="unlink">Unlink identity</button></form></div>'+creation_form(csrf)

def creation_form(csrf):
    fields='<h2>Create CUCM account</h2><div class="panel"><form method="post">'+csrf+'<input type="hidden" name="action" value="create-cucm">'
    for key,label,kind in [('username','Existing portal username','text'),('userid','New CUCM user ID','text'),('first_name','First name','text'),('last_name','Last name','text'),('cucm_password','New CUCM password','password'),('cucm_pin','New CUCM PIN (optional)','password')]: fields+='<label>'+label+'</label><input name="'+key+'" type="'+kind+'" autocomplete="off">'
    return fields+'<label>Confirm creation</label><select name="confirm"><option value="no">No</option><option value="yes">Yes</option></select><br><button>Create and link CUCM user</button></form><p>Creates a local CUCM end user with Standard CCM End Users access. Password and PIN are not stored. This does not assign extensions, phones, voicemail or LDAP synchronization. Deleting the portal user does not delete the CUCM user.</p></div>'

def account_action(app,user,data):
    if data.get('action')=='voice-refresh': return account_refresh(app,user)

def account_link(app,user,identifier):
    return admin_change(app,{"username":user["username"],"userid":identifier,"action":"link"},None)
