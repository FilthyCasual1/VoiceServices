"""Dependency-free vSphere SOAP management; credentials used only for this request."""
import html,json,re,ssl,time
from http.cookiejar import CookieJar
from urllib.request import Request,build_opener,HTTPCookieProcessor,HTTPSHandler
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET
E=lambda value:html.escape(str(value),quote=True)
N={'v':'urn:vim25','s':'http://schemas.xmlsoap.org/soap/envelope/'}

class Client:
    def __init__(self,host,username,password,lab=False):
        parsed=urlsplit(host)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment: raise ValueError('Enter an HTTPS host origin, without a path or credentials.')
        self.endpoint=host.rstrip('/')+'/sdk'
        context=ssl._create_unverified_context() if lab else ssl.create_default_context()
        self.opener=build_opener(HTTPSHandler(context=context),HTTPCookieProcessor(CookieJar()))
        self.content=self.call('RetrieveServiceContent','<_this type="ServiceInstance">ServiceInstance</_this>').find('v:returnval',N)
        if self.content is None: raise ValueError('No vSphere service content returned.')
        self.manager=self.ref('sessionManager')
        self.call('Login',self.manager+'<userName>'+E(username)+'</userName><password>'+E(password)+'</password>')
    def ref(self,key):
        value=self.content.find('v:'+key,N)
        if value is None: raise ValueError('Missing vSphere reference: '+key)
        return '<_this type="'+E(value.attrib['type'])+'">'+E(value.text)+'</_this>'
    def call(self,method,body):
        envelope=('<?xml version="1.0"?><soapenv:Envelope xmlns:soapenv="'+N['s']+'" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><soapenv:Body><'+method+' xmlns="urn:vim25">'+body+'</'+method+'></soapenv:Body></soapenv:Envelope>').encode()
        request=Request(self.endpoint,data=envelope,headers={'Content-Type':'text/xml; charset=utf-8','SOAPAction':'"urn:vim25/6.0"'})
        try:
            try: response=self.opener.open(request,timeout=15)
            except HTTPError as exc: response=exc
            with response: raw=response.read(16*1024**2+1)
            if len(raw)>16*1024**2 or b'<!DOCTYPE' in raw or b'<!ENTITY' in raw: raise ValueError('Invalid or oversized vSphere response.')
            tree=ET.fromstring(raw);fault=tree.find('.//s:Fault',N)
            if fault is not None: raise ValueError('ESXi request rejected: '+(fault.findtext('faultstring') or 'API fault'))
            value=tree.find('s:Body',N)
            if value is None or len(value)!=1: raise ValueError('Invalid vSphere SOAP response.')
            return value[0]
        except (URLError,ET.ParseError,OSError) as exc: raise ValueError('ESXi connection failed. Check address, certificate, credentials and network access.') from exc
    def close(self):
        try: self.call('Logout',self.manager)
        except ValueError: pass
    def inventory(self):
        root=self.content.find('v:rootFolder',N)
        created=self.call('CreateContainerView',self.ref('viewManager')+'<container type="Folder">'+E(root.text)+'</container><type>VirtualMachine</type><type>HostSystem</type><type>Datastore</type><recursive>true</recursive>')
        view=created.findtext('v:returnval',namespaces=N)
        paths={'VirtualMachine':['name','runtime.powerState','config.hardware.numCPU','config.hardware.memoryMB'],'HostSystem':['name','summary.config.product.fullName','summary.hardware.numCpuThreads','summary.hardware.memorySize'],'Datastore':['name','summary.capacity','summary.freeSpace']}
        specs=''.join('<propSet><type>'+kind+'</type><all>false</all>'+''.join('<pathSet>'+p+'</pathSet>' for p in props)+'</propSet>' for kind,props in paths.items())
        specs+='<objectSet><obj type="ContainerView">'+E(view)+'</obj><skip>true</skip><selectSet xsi:type="TraversalSpec"><name>viewTraversal</name><type>ContainerView</type><path>view</path><skip>false</skip></selectSet></objectSet>'
        rows=[]
        try:
            result=self.call('RetrievePropertiesEx',self.ref('propertyCollector')+'<specSet>'+specs+'</specSet><options><maxObjects>200</maxObjects></options>')
            while True:
                for obj in result.findall('v:returnval/v:objects',N):
                    ref=obj.find('v:obj',N);values={p.findtext('v:name',namespaces=N):p.findtext('v:val',namespaces=N) for p in obj.findall('v:propSet',N)}
                    rows.append(dict(id=ref.text,type=ref.attrib['type'],values=values))
                token=result.findtext('v:returnval/v:token',namespaces=N)
                if not token: return rows
                if len(rows)>10000: raise ValueError('Inventory exceeds the portal limit.')
                result=self.call('ContinueRetrievePropertiesEx',self.ref('propertyCollector')+'<token>'+E(token)+'</token>')
        finally:
            try: self.call('DestroyView','<_this type="ContainerView">'+E(view)+'</_this>')
            except ValueError: pass
    def power(self,identifier,action):
        methods={'power-on':'PowerOnVM_Task','shutdown':'ShutdownGuest','suspend':'SuspendVM_Task','power-off':'PowerOffVM_Task'}
        if action not in methods or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}',identifier): raise ValueError('Invalid VM action.')
        result=self.call(methods[action],'<_this type="VirtualMachine">'+E(identifier)+'</_this>')
        task=result.findtext('v:returnval',namespaces=N)
        return 'Request accepted'+(' (task '+task+')' if task else '')+'. Refresh inventory to verify the outcome.'

def settings(app):
    with app.store.connect() as db:
        row=db.execute("SELECT value FROM portal_settings WHERE key='esxi'").fetchone()
        return json.loads(row[0]) if row else {'host':'','username':'','lab':False}
def admin_change(app,data,services):
    host=data.get('host','').strip();parsed=urlsplit(host)
    if parsed.scheme!='https' or not parsed.hostname or parsed.path not in ('','/') or parsed.username or parsed.password or parsed.query or parsed.fragment: raise ValueError('Use an HTTPS host origin.')
    values={'host':host,'username':data.get('username','')[:100],'lab':data.get('lab')=='yes'}
    with app.store.connect() as db: db.execute("INSERT OR REPLACE INTO portal_settings VALUES('esxi',?)",(json.dumps(values),))
    return 'Connection defaults saved. Passwords are never stored.'
def admin_render(app,user,services):
    value=settings(app);csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
    return '<div class="panel"><form method="post">'+csrf+'<label>ESXi HTTPS address</label><input name="host" type="url" value="'+E(value['host'])+'" required><label>ESXi username</label><input name="username" value="'+E(value['username'])+'"><label>Certificate validation</label><select name="lab"><option value="no">Verify certificate</option><option value="yes"'+(' selected' if value['lab'] else '')+'>Lab: allow untrusted certificate</option></select><br><button>Save connection defaults</button></form><p><a href="/esxi">Open ESXi management</a>. Host credentials are supplied for each inventory or control request and are never saved. API access depends on host licensing and account privileges.</p></div>'
def page(app,path,method,data,user,env,send):
    if path!='/esxi': return None
    if user['role']!='admin': return send('403 Forbidden',app.page('Access denied','Administrator access required.',user))
    value=settings(app);csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">';content=''
    if method=='POST':
        client=None
        try:
            client=Client(value['host'],value['username'],data.get('password',''),value['lab'])
            action=data.get('action','inventory')
            if action!='inventory':
                if data.get('confirm')!='yes': raise ValueError('Confirm the selected VM power operation.')
                content+='<p class="notice">'+E(client.power(data.get('vm',''),action))+'</p>'
            rows=client.inventory()
            content+='<table><tr><th>Type</th><th>Name</th><th>ID</th><th>Details</th></tr>'
            for row in rows:
                details='; '.join(k+': '+str(v) for k,v in row['values'].items() if k!='name')
                content+='<tr><td>'+E(row['type'])+'</td><td>'+E(row['values'].get('name',''))+'</td><td>'+E(row['id'])+'</td><td>'+E(details)+'</td></tr>'
            content+='</table>'
        except ValueError as exc: content+='<p class="notice error">'+E(exc)+'</p>'
        finally:
            if client: client.close()
    content+='<div class="panel"><p>Connection: '+E(value['host'] or 'Not configured')+'; user: '+E(value['username'])+'</p><form method="post">'+csrf+'<label>ESXi password</label><input type="password" name="password" autocomplete="off" required><label>Operation</label><select name="action"><option value="inventory">Refresh inventory</option><option value="power-on">Power on VM</option><option value="shutdown">Shut down guest</option><option value="suspend">Suspend VM</option><option value="power-off">Power off VM</option></select><label>VM ID (for power operations)</label><input name="vm"><label>Confirm VM operation</label><select name="confirm"><option value="no">No</option><option value="yes">Yes</option></select><br><button>Submit request</button></form><p><a href="/admin/esxi">Configure host</a>. Guest shutdown requires VMware Tools. Task acceptance does not mean completion.</p></div>'
    return send('200 OK',app.page('ESXi Management',content,user))
