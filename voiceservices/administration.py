"""Permanent administrator shell with addon-provided subpages."""
import html
from .modules import CATALOG
from . import branding,overview,user_management,notifications,recovery,maintenance
E=lambda value:html.escape(str(value),quote=True)
OPTIONAL={'voice':'voice','settings':'server-management','downloads':'downloads','pxe':'pxe','updates':'ftp-updates','esxi':'esxi'}
HEADINGS={'recovery':'Account recovery','notifications':'Send notifications','voice':'Phone account links','overview':'System overview','settings':'Service configuration','users':'User accounts','addons':'Addons','updates':'Update repository','downloads':'Internal tool downloads','pxe':'Network boot and restoration','esxi':'ESXi management','branding':'Look and Feel','home':'Home page blocks'}
def password_form(user):
    csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
    return '<div class="panel login"><form method="post">'+csrf+'<input type="hidden" name="action" value="password"><label>Current password</label><input name="current_password" type="password" autocomplete="current-password" required><label>New password</label><input name="new_password" type="password" minlength="12" autocomplete="new-password" required><label>Confirm new password</label><input name="confirm_password" type="password" minlength="12" autocomplete="new-password" required><br><button>Change password</button></form></div>'
def render(app,path,user,data,method,services):
    if user['role']!='admin': raise PermissionError('Administrator access required.')
    section=path.removeprefix('/admin').strip('/') or 'overview'
    if section not in HEADINGS: raise ValueError('Unknown administration submenu.')
    csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">';note=''
    if method=='POST':
        if section=='overview': note=maintenance.change(app,user,data)
        elif section=='addons':
            if data.get('action')!='remove': raise ValueError('Upload a package file to install an addon.')
            app.modules.change(data.get('module',''),False);note='Addon uninstalled. Files removed; saved data retained.'
        elif section=='recovery': note=recovery.issue(app,user,data)
        elif section=='notifications': note=notifications.change(app,user,data)
        elif section=='users': note=user_management.change(app,user,data)
        elif section in ('branding','home'): note=branding.change(app,section,data)
        elif section in OPTIONAL: note=app.modules.load(OPTIONAL[section]).admin_change(app,data,services)
        else: raise ValueError('Unknown administration action.')
    content='<h2>'+HEADINGS[section]+'</h2>'
    if note: content+='<p class="notice">'+E(note)+'</p>'
    if section=='overview': content+=overview.render(app)+maintenance.render(app,user)
    elif section in ('branding','home'): content+=branding.render(app,section,user)
    elif section=='recovery': content+=recovery.render(app,user)
    elif section=='notifications': content+=notifications.render(app,user)
    elif section=='users': content+=user_management.render(app,user)
    elif section in OPTIONAL: content+=app.modules.load(OPTIONAL[section]).admin_render(app,user,services)
    elif section=='addons':
        content+='<div class="panel"><form action="/admin/addons/upload" method="post" enctype="multipart/form-data">'+csrf+'<label>Addon package (.sraddon)</label><input type="file" name="file" accept=".sraddon" required><br><button>Install package</button></form><p>Install official packages built for this core release. Installation adds executable module files; uninstall removes them.</p></div>'
        for key,(name,description) in CATALOG.items():
            present=(app.modules.root/key).exists()
            if not present: continue
            installed=app.modules.installed(key)
            content+='<div class="panel"><h3>'+E(name)+'</h3><p>'+E(description)+'</p><p>'+('Installed' if installed else 'Incompatible package; uninstall before replacement')+'</p>'
            if present: content+='<form method="post">'+csrf+'<input type="hidden" name="module" value="'+key+'"><button name="action" value="remove">Uninstall package</button></form>'
            content+='</div>'
    links=[('/admin','Overview'),('/admin/users','Users and passwords'),('/admin/notifications','Notifications'),('/admin/recovery','Account recovery'),('/admin/addons','Addons'),('/admin/branding','Look and Feel'),('/admin/home','Home page blocks')]
    for section,module in OPTIONAL.items():
        if app.modules.installed(module): links.append(('/admin/'+section,HEADINGS[section]))
    sidebar='<aside class="admin-nav"><h3>Administration</h3>'+''.join('<a href="'+url+'">'+label+'</a>' for url,label in links)+'</aside>'
    return '<div class="admin-layout">'+sidebar+'<div class="admin-content">'+content+'</div></div>'
