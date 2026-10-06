"""Administrator controls for the installed host update provider."""
import html
E=lambda v:html.escape(str(v),quote=True)
def change(app,user,data):
    if user['role']!='admin': raise PermissionError('Administrator access required.')
    if not app.store.accounts: raise ValueError('One-click updates require a supported host update provider.')
    kind=data.get('update','')
    if kind not in ('os','insap','insap-install','insap-decline','vmtools','vmtools-cd'): raise ValueError('Choose OS, INSAP or guest-tools update.')
    if kind=='insap-decline':
        app.store.accounts.call('maintenance-decline','',data.get('release',''));return 'This INSAP version was declined. Future checks will leave it skipped.'
    app.store.accounts.call('maintenance-start',kind,data.get('release','') if kind=='insap-install' else '')
    if kind=='insap':return 'Fetching the available release and changelog. Progress updates automatically. Review it before installing.'
    return 'Update started. Progress updates automatically. The portal briefly disconnects while INSAP restarts.'
def render(app,user,started=False):
    from .version import __version__
    from . import distro,host_branding
    host=distro.detected();name=host.get('NAME',host.get('ID','Linux'));release=host.get('VERSION_ID','')
    identity=E((name+' '+release).strip())
    content='<div class="panel host-updates"><div class="distro-powered"><span>ServiceReady is powered by:</span>'+host_branding.marks()+'<span class="update-version">'+identity+'</span><span class="update-version">INSAP '+E(__version__)+'</span></div><p>Update host packages, INSAP or VM tools. Settings are retained; INSAP updates briefly restart the portal.</p>'
    if not app.store.accounts: return content+'<p class="muted">No host update provider is connected. One-click updates are unavailable on this deployment.</p><div class="update-actions"><button disabled>Update OS</button><button disabled>Grab INSAP update</button></div></div>'
    content+='<p class="muted">Connected update provider: host operating system.</p>'
    try: state=app.store.accounts.call('maintenance-status','','')
    except ValueError as exc: return content+'<p class="notice error">'+E(exc)+'</p></div>'
    review=state.get('review',{})
    if not isinstance(review,dict):review={}
    watch='starting' if started else state.get('state','idle')
    content=content.replace('class="panel host-updates"','class="panel host-updates" data-update-state="'+E(watch)+'" data-update-version="'+E(__version__)+'" data-review="'+E(review.get('commit','')+':'+review.get('state',''))+'"')
    content+='<p class="notice" data-update-status role="status" aria-live="polite">'+E(state.get('state','idle'))+': '+E(state.get('message','No updates started.'))+'</p>'
    content+='<div class="update-actions">'
    for kind,label in [('os','Update OS'),('insap','Grab INSAP update'),('vmtools','Update VM tools')]: content+='<form class="inline" method="post" action="/admin/host" data-start-update><input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><button name="update" value="'+kind+'"'+(' disabled' if state.get('state')=='running' else '')+'>'+label+'</button></form>'
    cd=state.get('tools_cd',{})
    if isinstance(cd,dict) and cd:
        content+='<form class="inline" method="post" action="/admin/host" data-start-update><input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><button name="update" value="vmtools-cd">Install tools CD '+E(cd.get('version',''))+'</button></form>'
    content+='</div>'
    if review.get('state')=='ready':
        content+='<div class="release-review"><h3>INSAP '+E(review.get('version',''))+' — release review</h3><details open><summary>Changelog</summary><pre>'+E(review.get('changelog',''))+'</pre></details><form method="post" action="/admin/host" data-start-update><input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><input type="hidden" name="release" value="'+E(review.get('commit',''))+'"><div class="update-actions"><button name="update" value="insap-install">Proceed with update</button><button name="update" value="insap-decline">Decline this version</button></div></form></div>'
    elif review.get('state')=='declined':content+='<p class="muted">INSAP '+E(review.get('version',''))+' declined. A newer version will be offered on the next check.</p>'
    log=state.get('tools_log','')
    if isinstance(log,str) and log:content+='<details class="release-review tools-installer-output"'+(' open' if state.get('state')=='failed' else '')+'><summary>Installer output</summary><pre>'+E(log)+'</pre></details>'
    return content+'<details class="update-help"><summary>Update details</summary><p>INSAP uses the approved main branch and refreshes installed addons. VMware tools use host repositories. VirtualBox uses repository packages or verified Oracle images matching the hypervisor; Insert the Guest Additions CD for initial installation; the portal detects and verifies it before installing. Configure automatic updates below. OS or guest-driver updates may require a restart; updates never reboot automatically.</p></details></div>'
