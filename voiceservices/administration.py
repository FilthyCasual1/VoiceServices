"""Permanent administrator shell with addon-provided subpages."""
import html
from .modules import CATALOG
from . import branding,overview,user_management,notifications,recovery,maintenance,security,update_schedule,external_auth,host_tools,host_configuration,addon_updates
E=lambda value:html.escape(str(value),quote=True)
OPTIONAL={'snmp':'snmp','smtp':'smtp-notifications','voice':'voice','settings':'server-management','downloads':'downloads','pxe':'pxe','updates':'ftp-updates','esxi':'esxi'}
HEADINGS={'system-updates':'Portal and host updates','storage':'Upload storage','network-host':'Network and time','host':'Host maintenance','terminal':'Host terminal','authentication':'Account authentication','snmp':'SNMP monitoring','schedules':'Update schedules','security':'Security','smtp':'SMTP notifications','recovery':'Account recovery','notifications':'Send notifications','voice':'Phone account links','overview':'System overview','settings':'Service configuration','users':'Users and Accounts','addons':'Addons','updates':'Update repository','downloads':'Internal tool downloads','pxe':'Network boot and restoration','esxi':'ESXi management','branding':'Appearance','home':'Home page blocks'}
def password_form(user,app):
    if external_auth.identity(app,user): return '<p>Your password is managed by your identity provider.</p>'
    csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
    return '<div class="panel login"><form method="post">'+csrf+'<input type="hidden" name="action" value="password"><label>Current password</label><input name="current_password" type="password" autocomplete="current-password" required><label>New password</label><input name="new_password" type="password" minlength="12" autocomplete="new-password" required><label>Confirm new password</label><input name="confirm_password" type="password" minlength="12" autocomplete="new-password" required><br><button>Change password</button></form></div>'
def render(app,path,user,data,method,services):
    if user['role']!='admin': raise PermissionError('Administrator access required.')
    section=path.removeprefix('/admin').strip('/') or 'overview'
    if section in ('terminal','schedules','system-updates'): section='host'
    if section not in HEADINGS: raise ValueError('Unknown administration submenu.')
    csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">';note=''
    if method=='POST':
        if section in ('storage','network-host'): note=host_configuration.change(app,user,data)
        elif section=='host': note=update_schedule.change(app,user,data) if data.get('action')=='save-update-schedules' or path.rstrip('/')=='/admin/schedules' else maintenance.change(app,user,data)
        elif section=='addons' and data.get('action')=='install-repository-addon':note=addon_updates.install_from_repository(app,user,data)
        elif section=='addons' and data.get('action') in ('check-addon-update','install-addon-update','decline-addon-update'):note=addon_updates.change(app,user,data)
        elif section=='addons':
            if data.get('action')!='remove': raise ValueError('Upload a package file to install an addon.')
            app.modules.change(data.get('module',''),False);note='Addon uninstalled. Files removed; saved data retained.'
        elif section=='recovery': note=recovery.issue(app,user,data)
        elif section=='notifications': note=notifications.change(app,user,data)
        elif section=='schedules': note=update_schedule.change(app,user,data)
        elif section=='security': note=security.change(app,user,data)
        elif section=='authentication': note=external_auth.change(app,user,data)
        elif section=='users': note=recovery.issue(app,user,data) if data.get('action')=='authorize-recovery' else user_management.change(app,user,data)
        elif section in ('branding','home'): note=branding.change(app,section,data)
        elif section in OPTIONAL: note=app.modules.load(OPTIONAL[section]).admin_change(app,data,services)
        else: raise ValueError('Unknown administration action.')
    content='' if section=='overview' else '<h2>'+HEADINGS[section]+'</h2>'
    if note: content+='<p class="notice">'+E(note)+'</p>'
    if section=='overview': content+=overview.render(app)

    elif section in ('branding','home'): content+=branding.render(app,section,user)
    elif section=='recovery': content+=recovery.render(app,user)
    elif section=='notifications': content+=notifications.render(app,user)
    elif section=='schedules': content+=update_schedule.render(app,user)
    elif section=='security': content+=security.render(app,user)
    elif section=='authentication': content+=external_auth.render(app,user)
    elif section=='users': content+=user_management.render(app,user)+'<details class="settings-section" id="recovery"'+(' open' if data.get('action')=='authorize-recovery' else '')+'><summary>Account recovery</summary><div class="panel">'+recovery.render(app,user)+'</div></details>'
    elif section=='terminal': content+=host_tools.terminal_render(app,user)
    elif section=='host': content+='<h2>Portal and host updates</h2>'+maintenance.render(app,user,started=method=='POST' and bool(data.get('update')))+'<details class="settings-section" id="update-schedules"'+(' open' if data.get('action')=='save-update-schedules' else '')+'><summary>Automatic update schedules</summary>'+update_schedule.render(app,user)+'</details>'+'<details class="settings-section" id="terminal"'+(' open' if path.rstrip('/')=='/admin/terminal' else '')+'><summary>Host terminal</summary><div class="panel">'+host_tools.terminal_render(app,user)+'</div></details>'+host_tools.admin_render(app,user,services)
    elif section in ('storage','network-host'): content+=host_configuration.render(app,user,section)
    elif section in OPTIONAL: content+=app.modules.load(OPTIONAL[section]).admin_render(app,user,services)
    elif section=='addons':
        content+=addon_updates.repository_installer(app,user)
        content+='<div class="panel"><form action="/admin/addons/upload" method="post" enctype="multipart/form-data">'+csrf+'<h3>Manual installation</h3><label>Addon package (.sraddon)</label><input type="file" name="file" accept=".sraddon" required><br><button>Install package</button></form><p>Install official packages built for this core release. Installation adds executable module files; uninstall removes them.</p></div>'
        for key,(name,description) in CATALOG.items():
            present=(app.modules.root/key).exists()
            if not present: continue
            installed=app.modules.installed(key)
            content+='<div class="panel"><h3>'+E(name)+'</h3><p>'+E(description)+'</p><p>'+('Installed' if installed else 'Incompatible package; uninstall before replacement')+'</p>'
            if present: content+='<form method="post">'+csrf+'<input type="hidden" name="module" value="'+key+'"><button name="action" value="remove">Uninstall package</button></form>'
            if installed:content+=addon_updates.render(app,user,key)
            content+='</div>'
    administrator=[('/admin/authentication','Account authentication'),('/admin/users','Users and Accounts'),('/admin/notifications','Notifications')]
    operator=[('/admin/host','Host maintenance'),('/admin/storage','Upload storage'),('/admin/network-host','Network and time'),('/admin/security','Security'),('/admin/addons','Addons'),('/admin/branding','Appearance'),('/admin/home','Home page blocks')]
    for submenu,module in OPTIONAL.items():
        if app.modules.installed(module):
            (administrator if submenu=='voice' else operator).append(('/admin/'+submenu,HEADINGS[submenu]))
    def navigation_link(url,label):
        return '<a href="'+url+'"'+(' aria-current="page"' if path.rstrip('/')==url else '')+'>'+E(label)+'</a>'
    def tree(label,links):
        return '<details class="admin-tree" open><summary>'+label+'</summary><div>'+''.join(navigation_link(url,label) for url,label in links)+'</div></details>'
    sidebar='<aside class="admin-nav" aria-label="Administration"><h3>Administration</h3>'+navigation_link('/admin','Overview')+tree('Administrator',administrator)+tree('System',operator)+'</aside>'
    return '<div class="admin-layout">'+sidebar+'<div class="admin-content'+(' admin-overview' if section=='overview' else '')+'">'+content+'</div></div>'
