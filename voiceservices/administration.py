"""Administration submenus and persistent operator settings."""
import html
import json
import time
from urllib.parse import urlsplit
from .modules import CATALOG
E=lambda value:html.escape(str(value),quote=True)

def password_form(user):
    return '<div class="panel login"><form method="post"><input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><input type="hidden" name="action" value="password"><label>Current password</label><input name="current_password" type="password" autocomplete="current-password" required><label>New password</label><input name="new_password" type="password" minlength="12" autocomplete="new-password" required><label>Confirm new password</label><input name="confirm_password" type="password" minlength="12" autocomplete="new-password" required><br><button>Change password</button></form></div>'

def render(app,path,user,data,method,services):
    if user['role']!='admin': raise PermissionError('Administrator access required.')
    section=path.removeprefix('/admin').strip('/') or 'overview'
    if section not in ('overview','settings','users','addons','updates','downloads','pxe'): raise ValueError('Unknown administration submenu.')
    csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
    note=''
    if method=='POST':
        action=data.get('action')
        if section=='addons':
            if action not in ('install','remove'): raise ValueError('Unknown addon action.')
            module=data.get('module','ftp-updates')
            if module=='ftp-updates':
                if action=='install': app.updates.install()
                else: app.updates.remove()
            else: app.modules.change(module,action=='install')
            note='Module '+('installed.' if action=='install' else 'removed. Saved data is retained.')
        elif section=='downloads':
            if action=='remove-link': app.downloads.remove_link(data.get('link',''))
            else: app.downloads.add_link(data)
            note='Download catalog saved.'
        elif section=='pxe': app.pxe.change(data);note='Boot settings saved.'
        elif section=='updates': app.updates.configure(data);note='FTP settings saved. The installed worker applies changes automatically.'
        elif section=='settings':
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
        else: raise ValueError('Unknown administration action.')
    headings={'overview':'System overview','settings':'Service configuration','users':'User accounts','addons':'Installable addons','updates':'Update repository','downloads':'Internal tool downloads','pxe':'Network boot and restoration'}
    content='<h2>'+headings[section]+'</h2>'
    if note: content+='<p class="notice">'+E(note)+'</p>'
    if section=='overview':
        content+='<p>Manage service connections, user accounts, and optional modules using the administration menu.</p><table><tr><th>Application</th><th>Configuration / access</th></tr>'
        for key,label,_ in (services if app.modules.installed('server-management') else []):
            url=app.config.get('services',{}).get(key,'')
            content+='<tr><td>'+E(label)+'</td><td>'+('<a href="'+E(url)+'" rel="noopener noreferrer">Open application</a> — health unverified' if app.valid_link(url) else 'Not configured')+'</td></tr>'
        content+='</table>' if app.modules.installed('server-management') else '</table><p>Server Management is not installed. Manage available modules in <a href="/admin/addons">Addons</a>.</p>'
    elif section=='settings':
        content+='<div class="panel"><form method="post">'+csrf
        for key,label,_ in services:
            content+='<label>'+E(label)+' URL</label><input name="'+key+'" type="url" value="'+E(app.config.get('services',{}).get(key,''))+'">'
        setup=app.config.get('self_provisioning',{})
        for key,label,value in ([('tftp_host','Phone provisioning server',app.config.get('tftp_host','')),('jabber_domain','Messaging domain',app.config.get('jabber_domain','')),('ivr_number','Self-provisioning number',setup.get('ivr_number','')),('network','Phone network / VLAN',setup.get('network',''))] if app.modules.installed('voice') else []):
            content+='<label>'+label+'</label><input name="'+key+'" value="'+E(value)+'">'
        content+='<br><button>Save settings</button></form></div>'
    elif section=='users':
        backend='Alpine system accounts' if app.store.accounts else 'Local portal accounts'
        content+='<p>Authentication: <strong>'+backend+'</strong>. <a href="/account">Change your password</a>.</p><table><tr><th>Username</th><th>Portal access</th></tr>'
        with app.store.connect() as db:
            for row in db.execute('SELECT username,role FROM users ORDER BY username'): content+='<tr><td>'+E(row['username'])+'</td><td>'+E(row['role'])+'</td></tr>'
        content+='</table><p class="muted">System passwords are managed by Alpine when system authentication is configured. Only enrolled system accounts can sign in. Portal roles remain separate from operating-system permissions.</p>'
    elif section=='addons':
        for key,(name,description) in CATALOG.items():
            installed=app.modules.installed(key)
            content+='<div class="panel"><h3>'+E(name)+'</h3><p>'+E(description)+'</p><p>'+('Installed' if installed else 'Not installed')+'</p><form method="post">'+csrf+'<input type="hidden" name="module" value="'+key+'"><button name="action" value="'+('remove' if installed else 'install')+'">'+('Remove module' if installed else 'Install module')+'</button></form></div>'
        installed=app.updates.settings() is not None
        content+='<div class="panel"><h3>FTP Update Repository</h3><p>Upload update packages through this portal and let managed applications retrieve them from a read-only FTP server.</p><p>Status: '+('Installed' if installed else 'Not installed')+'</p><form method="post">'+csrf+'<input type="hidden" name="module" value="ftp-updates"><button name="action" value="'+('remove' if installed else 'install')+'">'+('Remove addon' if installed else 'Install addon')+'</button></form>'+('<p><a href="/admin/updates">Configure and upload files</a></p>' if installed else '')+'</div>'
    elif section=='downloads':
        content+='<div class="panel"><form method="post">'+csrf
        for key,label in [('title','Application / tool name'),('version','Version'),('platform','Operating system / platform'),('url','Download URL')]: content+='<label>'+label+'</label><input name="'+key+'"'+(' type="url"' if key=='url' else '')+' required>'
        content+='<br><button>Add download link</button></form></div><h2>Catalog links</h2><table><tr><th>Title</th><th>Action</th></tr>'
        for item in app.downloads.catalog(): content+='<tr><td>'+E(item['title'])+'</td><td><form method="post">'+csrf+'<input type="hidden" name="link" value="'+str(item['id'])+'"><button name="action" value="remove-link">Remove link</button></form></td></tr>'
        content+='</table><h2>Upload a tool or application</h2><div class="panel"><form action="/admin/downloads/upload" method="post" enctype="multipart/form-data">'+csrf+'<label>Package file</label><input name="file" type="file" required><br><button>Upload package</button></form><p>Uploaded packages and catalog links are available to guests in Downloads. Use this module for files intended for your internal network.</p></div>'+app.downloads.render()
    elif section=='pxe': content+=app.pxe.render(user)
    elif section=='updates':
        settings=app.updates.settings()
        if settings is None: content+='<p><a href="/admin/addons">Install the FTP update addon</a> to use this page.</p>'
        else:
            status='Disabled'
            if settings.get('enabled'):
                status='Enabled; worker not yet verified'
                with app.store.connect() as db:
                    exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='addon_status'").fetchone()
                    if exists:
                        row=db.execute("SELECT status,at FROM addon_status WHERE id='ftp-updates'").fetchone()
                        if row and row['at']>time.time()-10: status=row['status']
            content+='<p class="notice">'+E(status)+'. Applications pull files from this repository; installation and reboot remain in their native upgrade screen. FTP is unencrypted; restrict it to your testbed network.</p><div class="panel"><form method="post">'+csrf
            for key,label,kind in [('username','FTP username','text'),('port','Control port','number'),('passive_start','First passive port','number'),('passive_end','Last passive port','number'),('address','Advertised address (optional)','text')]:
                content+='<label>'+label+'</label><input name="'+key+'" type="'+kind+'" value="'+E(settings.get(key,''))+'">'
            content+='<label>FTP password (leave blank to retain)</label><input name="ftp_password" type="password" autocomplete="new-password"><label>FTP server</label><select name="enabled"><option value="no">Disabled</option><option value="yes"'+(' selected' if settings.get('enabled') else '')+'>Enabled</option></select><br><button>Save FTP settings</button></form></div>'
            host=settings.get('address') or urlsplit(app.base).hostname
            content+='<h2>Upgrade source details</h2><div class="panel">Server: '+E(host)+'<br>Port: '+E(settings['port'])+'<br>Directory: /<br>Username: '+E(settings['username'])+'<p>Use Remote Filesystem with FTP in your application upgrade workflow. Supply the password configured above. Use the uploaded filename listed below.</p></div>'
            content+='<h2>Upload an update file</h2><div class="panel"><form action="/admin/updates/upload" method="post" enctype="multipart/form-data">'+csrf+'<label for="update-file">Package file</label><input id="update-file" name="file" type="file" required><br><button>Upload file</button></form><p>Maximum file size: '+E(app.updates.limit//1024**2)+' MiB. Existing filenames are never overwritten.</p></div><table><tr><th>Filename</th><th>Bytes</th><th>SHA-256</th></tr>'
            for row in app.updates.files(): content+='<tr><td>'+E(row['name'])+'</td><td>'+str(row['size'])+'</td><td><code>'+E(row['sha256'])+'</code></td></tr>'
            content+='</table>'
    links=[('/admin','Overview'),('/admin/settings','Service settings'),('/admin/users','Users and passwords'),('/admin/addons','Addons'),('/admin/updates','Update files')]
    if not app.modules.installed('server-management'): links=[item for item in links if item[0]!='/admin/settings']
    if app.updates.settings() is None: links=[item for item in links if item[0]!='/admin/updates']
    if app.modules.installed('downloads'): links.append(('/admin/downloads','Downloads'))
    if app.modules.installed('pxe'): links.append(('/admin/pxe','PXE and images'))
    sidebar='<aside class="admin-nav"><h3>Administration</h3>'+''.join('<a href="'+url+'">'+label+'</a>' for url,label in links)+'</aside>'
    return '<div class="admin-layout">'+sidebar+'<div class="admin-content">'+content+'</div></div>'
