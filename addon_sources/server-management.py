import html,json,time
from urllib.parse import urlencode,urlsplit
E=lambda value:html.escape(str(value),quote=True)
SERVICES = [
    ('cucm_admin','Call Management','admin'),
    ('cucm_serviceability','Call Service Tools','admin'),
    ('cucm_os','Call Server Settings','admin'),
    ('cucm_drs','Call Server Backup','admin'),
    ('self_care','Self Care','user'),
    ('cuc_admin','Voicemail Management','admin'),
    ('cuc_serviceability','Voicemail Service Tools','admin'),
    ('imp_admin','Messaging Management','admin'),
    ('imp_serviceability','Messaging Service Tools','admin'),
    ('openwrt','Network Management','admin'),
]

def page(app,path,method,data,user,env,send):
    if path=="/network": return send("200 OK",app.page("Network Management",'<p class="notice">Adapter not connected.</p>',user))

def admin_render(app,user,services):
    csrf='<input type="hidden" name="csrf" value="'+E(user["csrf"])+'">'
    content=""
    content+='<div class="panel"><form method="post">'+csrf
    for key,label,_ in services:
        content+='<label>'+E(label)+' URL</label><input name="'+key+'" type="url" value="'+E(app.config.get('services',{}).get(key,''))+'">'
    setup=app.config.get('self_provisioning',{})
    for key,label,value in ([('tftp_host','Phone provisioning server',app.config.get('tftp_host','')),('jabber_domain','Messaging domain',app.config.get('jabber_domain','')),('ivr_number','Self-provisioning number',setup.get('ivr_number','')),('network','Phone network / VLAN',setup.get('network',''))] if app.modules.installed('voice') else []):
        content+='<label>'+label+'</label><input name="'+key+'" value="'+E(value)+'">'
    content+='<br><button>Save settings</button></form></div>'
    return content

def admin_change(app,data,services):
    values={}
    for key,label,_ in services:
        value=data.get(key,'').strip()
        if value and not app.valid_link(value): raise ValueError('Enter an HTTP(S) URL for '+label+'.')
        values[key]=value
    settings={'services':dict(app.config.get('services',{}),**values),'tftp_host':data.get('tftp_host','')[:200],'jabber_domain':data.get('jabber_domain','')[:200],
              'self_provisioning':dict(app.config.get('self_provisioning',{}),ivr_number=data.get('ivr_number','')[:40],network=data.get('network','')[:200])}
    if not app.modules.installed('voice'):
        for key in ('tftp_host','jabber_domain','self_provisioning'): settings.pop(key)
    with app.store.connect() as db:
        for key,value in settings.items(): db.execute('INSERT OR REPLACE INTO portal_settings VALUES(?,?)',(key,json.dumps(value)))
    app.config.update(settings);note='Settings saved.'
    return locals().get("note","Settings saved.")
