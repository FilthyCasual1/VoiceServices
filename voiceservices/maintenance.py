"""Administrator controls for the installed host update provider."""
import html
E=lambda v:html.escape(str(v),quote=True)
def change(app,user,data):
    if user['role']!='admin': raise PermissionError('Administrator access required.')
    if not app.store.accounts: raise ValueError('One-click updates require a supported host update provider.')
    kind=data.get('update','')
    if kind not in ('os','insap'): raise ValueError('Choose OS or INSAP update.')
    app.store.accounts.call('maintenance-start',kind,'')
    return 'Update started. Refresh this page to see progress.'
def render(app,user):
    content='<h2>Portal and host updates</h2><div class="panel host-updates"><img class="distro-logo" src="/host/distro-logo" alt="Host distribution logo"><p>OS updates use the installed host update provider to upgrade system packages. INSAP updates install the approved main branch, preserve settings, and refresh installed addons. Updating INSAP briefly restarts the portal.</p>'
    if not app.store.accounts: return content+'<p class="muted">No host update provider is connected. One-click updates are unavailable on this deployment.</p><button disabled>Update OS</button><button disabled>Update INSAP</button></div>'
    content+='<p class="muted">Connected update provider: Alpine Linux.</p>'
    try: state=app.store.accounts.call('maintenance-status','','')
    except ValueError as exc: return content+'<p class="notice error">'+E(exc)+'</p></div>'
    content+='<p class="notice">'+E(state.get('state','idle'))+': '+E(state.get('message','No updates started.'))+'</p>'
    for kind,label in [('os','Update OS'),('insap','Update INSAP')]: content+='<form class="inline" method="post"><input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><button name="update" value="'+kind+'"'+(' disabled' if state.get('state')=='running' else '')+'>'+label+'</button></form>'
    return content+'<p><a href="/admin">Refresh update status</a></p></div>'
