"""Administrator controls for the installed host update provider."""
import html
E=lambda v:html.escape(str(v),quote=True)
def change(app,user,data):
    if user['role']!='admin': raise PermissionError('Administrator access required.')
    if not app.store.accounts: raise ValueError('One-click updates require a supported host update provider.')
    kind=data.get('update','')
    if kind not in ('os','insap','insap-install','insap-decline','vmtools','vmtools-cd'): raise ValueError('Choose OS, INSAP or guest-tools update.')
    if kind in ('vmtools','vmtools-cd') and data.get('tools_provider'):
        provider=data['tools_provider']
        if provider not in ('virtualbox','vmware'):raise ValueError('Choose a supported hypervisor.')
        state=app.store.accounts.call('maintenance-status','','')
        if state.get('tools_provider')!=provider:raise ValueError('The selected hypervisor does not match this host. Check the VM platform before proceeding.')
        if kind=='vmtools-cd' and (provider!='virtualbox' or state.get('tools_cd',{}).get('provider')!=provider):raise ValueError('Insert a VirtualBox Guest Additions CD before proceeding.')
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
    live=state.get('tools_live',{})
    if isinstance(live,dict) and live.get('provider')=='virtualbox':
        versions='<span class="update-version">VirtualBox '+E(live.get('host_version') or 'version unavailable')+'</span><span class="update-version">Guest Additions '+E(live.get('version') or 'not detected')+'</span>'
        content=content.replace('<span class="update-version">INSAP '+E(__version__)+'</span>', '<span class="update-version">INSAP '+E(__version__)+'</span>'+versions)
        content+='<p class="tools-live-status">Guest tools now: <strong>VirtualBox '+E(live.get('version',''))+' — '+E(live.get('state','Unknown'))+'</strong></p>'
        if live.get('state')=='Running' and not live.get('communication',True):content+='<p class="muted">Guest service and driver are running. Hypervisor version property is unavailable; this does not indicate an installation failure.</p>'
    watch='starting' if started else state.get('state','idle')
    content=content.replace('class="panel host-updates"','class="panel host-updates" data-update-state="'+E(watch)+'" data-tools-result="'+E(str(state.get('kind',''))+':'+str(state.get('state',''))+':'+str(state.get('at',''))) +'" data-update-version="'+E(__version__)+'" data-review="'+E(review.get('commit','')+':'+review.get('state',''))+'"')
    content+='<p class="notice" data-update-status role="status" aria-live="polite">'+'Last host operation — '+E(state.get('state','idle'))+': '+E(state.get('message','No updates started.'))+'</p>'
    content+='<div class="update-actions">'
    for kind,label in [('os','Update OS'),('insap','Grab INSAP update')]: content+='<form class="inline" method="post" action="/admin/host" data-start-update><input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><button name="update" value="'+kind+'"'+(' disabled' if state.get('state')=='running' else '')+'>'+label+'</button></form>'
    content+='</div>'+tools_wizard(user,state)
    if review.get('state')=='ready':
        content+='<div class="release-review"><h3>INSAP '+E(review.get('version',''))+' — release review</h3><details open><summary>Changelog</summary><pre>'+E(review.get('changelog',''))+'</pre></details><form method="post" action="/admin/host" data-start-update><input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><input type="hidden" name="release" value="'+E(review.get('commit',''))+'"><div class="update-actions"><button name="update" value="insap-install">Proceed with update</button><button name="update" value="insap-decline">Decline this version</button></div></form></div>'
    elif review.get('state')=='declined':content+='<p class="muted">INSAP '+E(review.get('version',''))+' declined. A newer version will be offered on the next check.</p>'
    log=state.get('tools_log','')
    if isinstance(log,str) and log:content+='<details class="release-review tools-installer-output"'+(' open' if state.get('state')=='failed' else '')+'><summary>Installer output</summary><pre>'+E(log)+'</pre></details>'
    return content+'<details class="update-help"><summary>Update details</summary><p>INSAP uses the approved main branch and refreshes installed addons. VMware tools use host repositories. VirtualBox uses repository packages or verified Oracle images matching the hypervisor; Insert the Guest Additions CD for initial installation; the portal detects and verifies it before installing. Configure automatic updates below. OS or guest-driver updates may require a restart; updates never reboot automatically.</p></details></div>'

def tools_wizard(user,state):
    import re
    cd=state.get('tools_cd',{});cd=cd if isinstance(cd,dict) else {}
    detected=cd.get('version','') if cd.get('provider')=='virtualbox' else ''
    suffix=' '+detected if isinstance(detected,str) and re.fullmatch(r'\d+\.\d+\.\d+',detected) else ''
    provider=state.get('tools_provider',state.get('tools_live',{}).get('provider',''))
    choices=''.join('<option value="'+value+'"'+(' selected' if value==provider else '')+'>'+label+'</option>' for value,label in [('virtualbox','VirtualBox'),('vmware','VMware')])
    return ('<details class="tools-wizard"><summary>Set up or update VM tools</summary><form method="post" action="/admin/host" data-tools-wizard data-start-update>'
      '<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
      '<fieldset data-tools-step="0"><legend>1. Hypervisor</legend><p>Choose the platform running this VM. Detected: '+E(provider or 'Unknown')+'.</p><label>Hypervisor <select name="tools_provider">'+choices+'</select></label><button type="button" data-tools-next="1">Next</button></fieldset>'
      '<fieldset data-tools-step="1"><legend>2. Installation method</legend><label>Method <select name="update"><option value="vmtools">Update or install recommended tools</option><option value="vmtools-cd">Install tools CD'+E(suffix)+'</option></select></label><p>VMware uses the host repository package. VirtualBox uses detected media or verified Oracle downloads; initial installation requires its Guest Additions CD.</p><p>Detected media: '+E((cd.get('provider','')+' '+suffix).strip() or 'No tools CD inserted')+'.</p><button type="button" data-tools-next="0">Back</button><button type="button" data-tools-next="2">Next</button></fieldset>'
      '<fieldset data-tools-step="2"><legend>3. Review and install</legend><p data-tools-review>Confirm the selected hypervisor and method. Required dependencies will be installed automatically. Desktop/X.Org integration is optional. A restart may be needed; the portal will not restart the VM automatically.</p><button type="button" data-tools-next="1">Back</button><button type="submit"'+(' disabled' if state.get('state')=='running' else '')+'>Start tools setup</button></fieldset></form></details>')
