"""Administrator controls for the installed host update provider."""
import html
E=lambda v:html.escape(str(v),quote=True)
def change(app,user,data):
    if user['role']!='admin': raise PermissionError('Administrator access required.')
    if not app.store.accounts: raise ValueError('One-click updates require a supported host update provider.')
    kind=data.get('update','')
    if kind not in ('os','insap','vmtools'): raise ValueError('Choose OS, INSAP or guest-tools update.')
    app.store.accounts.call('maintenance-start',kind,'')
    return 'Update started. Progress updates automatically. The portal briefly disconnects while INSAP restarts.'
def render(app,user,started=False):
    from .version import __version__
    from . import distro
    host=distro.detected();name=host.get('NAME',host.get('ID','Linux'));release=host.get('VERSION_ID','')
    identity=E((name+' '+release).strip())
    content='<div class="panel host-updates"><div class="distro-powered"><span>Powered by</span><img class="distro-logo" src="/host/distro-logo" alt="Host distribution logo"><span class="update-version">'+identity+'</span><span class="update-version">INSAP '+E(__version__)+'</span></div><p>OS updates use the installed host update provider to upgrade system packages. INSAP updates install the approved main branch, preserve settings, and refresh installed addons. Updating INSAP briefly restarts the portal. VM tools update automatically on their own schedule below. VMware uses host repositories; VirtualBox uses repository packages or verified Oracle images matching the hypervisor version. Initial Oracle Guest Additions must already be installed. A reboot may be needed for guest drivers.</p>'
    if not app.store.accounts: return content+'<p class="muted">No host update provider is connected. One-click updates are unavailable on this deployment.</p><div class="update-actions"><button disabled>Update OS</button><button disabled>Update INSAP</button></div></div>'
    content+='<p class="muted">Connected update provider: host operating system.</p>'
    try: state=app.store.accounts.call('maintenance-status','','')
    except ValueError as exc: return content+'<p class="notice error">'+E(exc)+'</p></div>'
    watch='starting' if started else state.get('state','idle')
    content=content.replace('class="panel host-updates"','class="panel host-updates" data-update-state="'+E(watch)+'" data-update-version="'+E(__version__)+'"')
    content+='<p class="notice" data-update-status role="status" aria-live="polite">'+E(state.get('state','idle'))+': '+E(state.get('message','No updates started.'))+'</p>'
    content+='<div class="update-actions">'
    for kind,label in [('os','Update OS'),('insap','Update INSAP'),('vmtools','Update VM tools')]: content+='<form class="inline" method="post" action="/admin/host" data-start-update><input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><button name="update" value="'+kind+'"'+(' disabled' if state.get('state')=='running' else '')+'>'+label+'</button></form>'
    return content+'</div></div>'
