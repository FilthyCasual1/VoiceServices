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
    from .version import __version__, __display_version__
    from . import distro,host_branding
    host=distro.detected();name=host.get('NAME',host.get('ID','Linux'));release=host.get('VERSION_ID','')
    identity=E((name+' '+release).strip())
    content='<div class="panel host-updates"><div class="distro-powered"><span>ServiceReady is powered by:</span>'+host_branding.marks()+'<span class="update-version">'+identity+'</span><span class="update-version">INSAP '+E(__display_version__)+'</span></div><p>Update host packages, INSAP or VM tools. Settings are retained; INSAP updates briefly restart the portal.</p>'
    if not app.store.accounts: return content+'<p class="muted">No host update provider is connected. One-click updates are unavailable on this deployment.</p><div class="update-actions"><button disabled>Update OS</button><button disabled>Update INSAP</button></div></div>'
    content+='<p class="muted">Connected update provider: host operating system.</p>'
    try: state=app.store.accounts.call('maintenance-status','','')
    except ValueError as exc: return content+'<p class="notice error">'+E(exc)+'</p></div>'
    if state.get('provider')=='openwrt':return content+'<p class="notice">'+E(state['provider_message'])+'</p></div>'
    review=state.get('review',{})
    if not isinstance(review,dict):review={}
    live=state.get('tools_live',{})
    if isinstance(live,dict) and live.get('provider') in ('virtualbox','vmware'):
        platform,tools=('VMware','VMware Tools') if live['provider']=='vmware' else ('VirtualBox','Guest Additions')
        versions=''.join('<span class="update-version">'+label+' '+E(value)+'</span>' for label,value in [(platform,live.get('host_version')),(tools,live.get('version'))] if value)
        content=content.replace('<span class="update-version">INSAP '+E(__display_version__)+'</span>', '<span class="update-version">INSAP '+E(__display_version__)+'</span>'+versions)
        content+='<p class="tools-live-status">Guest tools now: <strong>'+platform+' '+E(live.get('version',''))+' — '+E(live.get('state','Unknown'))+'</strong></p>'
        if live.get('provider')=='virtualbox' and live.get('state')=='Running' and not live.get('communication',True):content+='<p class="muted">Guest service and driver are running. Hypervisor version property is unavailable; this does not indicate an installation failure.</p>'
    watch='starting' if started and state.get('state','idle')=='idle' else state.get('state','idle')
    content=content.replace('class="panel host-updates"','class="panel host-updates" data-update-state="'+E(watch)+'" data-tools-result="'+E(str(state.get('kind',''))+':'+str(state.get('state',''))+':'+str(state.get('at',''))) +'" data-update-version="'+E(__version__)+'" data-review="'+E(review.get('commit','')+':'+review.get('state',''))+'"')
    content+='<p class="notice" data-update-status role="status" aria-live="polite">'+'Last host operation — '+E(state.get('state','idle'))+': '+E(state.get('message','No updates started.'))+'</p>'
    content+='<div class="update-actions">'+update_wizard(user,state,'os')+update_wizard(user,state,'insap')+tools_wizard(user,state)+'</div>'
    log=state.get('tools_log','')
    if isinstance(log,str) and log:content+='<details class="release-review tools-installer-output"'+(' open' if state.get('state')=='failed' else '')+'><summary>Installer output</summary><pre>'+E(log)+'</pre></details>'
    return content+'<details class="update-help"><summary>Update details</summary><p>INSAP uses the approved main branch and refreshes installed addons. VMware tools use host repositories. VirtualBox uses repository packages or verified Oracle images matching the hypervisor; Insert the Guest Additions CD for initial installation; the portal detects and verifies it before installing. Configure automatic updates below. OS or guest-driver updates may require a restart; updates never reboot automatically.</p></details></div>'

def tools_wizard(user,state):
    import re
    cd=state.get('tools_cd',{});cd=cd if isinstance(cd,dict) else {}
    version=cd.get('version','')
    suffix=' '+version if cd.get('provider')=='virtualbox' and isinstance(version,str) and re.fullmatch(r'\d+\.\d+\.\d+',version) else ''
    provider=state.get('tools_provider',state.get('tools_live',{}).get('provider',''))
    choices=''.join('<label class="tools-choice"><input type="radio" name="tools_provider" value="'+value+'"'+(' checked' if value==provider or (provider not in ('virtualbox','vmware') and value=='virtualbox') else '')+'><img src="/static/provider-'+value+'.svg" alt=""><span><strong>'+label+'</strong><small>'+description+'</small></span></label>' for value,label,description in [('virtualbox','VirtualBox','Oracle Guest Additions'),('vmware','VMware','Repository-managed open-vm-tools')])
    return ('<button type="button" data-tools-open>VM tools setup…</button><dialog class="tools-wizard" aria-labelledby="tools-title"><header><h3 id="tools-title">VM tools setup</h3><button type="button" data-tools-close aria-label="Close wizard">×</button></header><form method="post" action="/admin/host" data-tools-wizard data-start-update>'
      '<input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><ol class="tools-steps"><li data-tools-marker="0" aria-current="step">Platform</li><li data-tools-marker="1">Method</li><li data-tools-marker="2">Review</li></ol>'
      '<fieldset data-tools-step="0"><legend>1. Hypervisor</legend><p>Choose the platform running this VM. Detected: '+E(provider or 'Unknown')+'.</p>'+choices+'<footer><button type="button" data-tools-close>Cancel</button><button type="button" data-tools-next="1">Next →</button></footer></fieldset>'
      '<fieldset data-tools-step="1"><legend>2. Installation method</legend><label class="tools-choice"><input type="radio" name="update" value="vmtools" checked><span><strong>Recommended installation / update</strong><small>VMware: host repository package. VirtualBox: detected media or verified Oracle image.</small></span></label><label class="tools-choice" data-tools-cd-choice><input type="radio" name="update" value="vmtools-cd"><span><strong>Install tools CD'+E(suffix)+'</strong><small>Use a verified VirtualBox Guest Additions disc. Insert the CD before continuing.</small></span></label><p>Detected media: '+E(cd.get('provider') or 'None')+E(suffix)+'.</p><footer><button type="button" data-tools-next="0">← Back</button><button type="button" data-tools-next="2">Next →</button></footer></fieldset>'
      '<fieldset data-tools-step="2"><legend>3. Review and install</legend><p data-tools-review></p><p>Dependencies install automatically. Desktop integration is optional. This operation will not restart your VM.</p><footer><button type="button" data-tools-next="1">← Back</button><button type="submit"'+(' disabled' if state.get('state')=='running' else '')+'>Install / update tools</button></footer></fieldset><p class="notice" data-tools-progress hidden role="status">Starting tools setup… Follow progress in the host operation panel.</p></form></dialog>')

def update_wizard(user,state,kind):
    review=state.get('review',{});review=review if isinstance(review,dict) else {}
    title='Update OS' if kind=='os' else 'Update INSAP';identifier='update-'+kind
    matching=state.get('kind') in (('os',) if kind=='os' else ('insap','insap-check'))
    running=matching and state.get('state')=='running'
    failed=matching and state.get('state')=='failed'
    ready=kind=='insap' and review.get('state')=='ready' and not running and not failed
    outcome='failed' if failed else review.get('state') if kind=='insap' else 'installed' if matching and state.get('state')=='complete' else None
    terminal=not running and outcome in ('current','installed','declined','failed')
    csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
    start='<button type="button" data-update-open="'+identifier+'">'+title+'</button>'
    header='<dialog id="'+identifier+'" class="tools-wizard" aria-labelledby="'+identifier+'-title"'+(' data-update-running' if running else ' data-update-result' if terminal else ' data-update-ready' if ready else '')+'><header><h3 id="'+identifier+'-title">'+title+'</h3><button type="button" data-tools-close aria-label="Close wizard">×</button></header>'
    if running:
        body='<div class="wizard-progress"><h3>Update in progress</h3><p data-update-status role="status" aria-live="polite">'+E(state.get('message','Working…'))+'</p><p>The operation continues if you close this window. Progress reconnects automatically when the portal restarts.</p><button type="button" data-tools-close>Close</button></div>'
    elif terminal:
        label={'current':'INSAP is up to date','installed':'Update succeeded','declined':'Update declined','failed':'Update did not complete'}[outcome]
        message=state.get('message','') if matching and outcome in ('installed','failed') else {'current':'No newer INSAP release is available. No changes were needed.','installed':'INSAP and installed addons updated successfully.','declined':'This version was skipped. Check again when a new release is available.','failed':'Check the host operation details before trying again.'}[outcome]
        body='<div class="wizard-progress"><h3>'+label+'</h3><p'+(' class="notice error"' if failed else '')+'>'+E(message)+'</p><form method="post" action="/admin/host" data-start-update>'+csrf+'<footer><button name="update" value="'+kind+'">'+('Run another OS update' if kind=='os' else 'Check again')+'</button><button type="button" data-tools-close>Finish</button></footer></form></div>'
    elif ready:
        body='<form method="post" action="/admin/host" data-start-update>'+csrf+'<input type="hidden" name="release" value="'+E(review.get('commit',''))+'"><ol class="tools-steps"><li>Check</li><li aria-current="step">Review</li><li>Finish</li></ol><h3>INSAP '+E(review.get('version',''))+' is available</h3><details open><summary>Changelog</summary><pre>'+E(review.get('changelog',''))+'</pre></details><p>Accounts, settings and installed addon data are retained. The portal briefly restarts.</p><footer><button name="update" value="insap-decline">Decline this version</button><button name="update" value="insap-install">Proceed with update</button></footer></form>'
    else:
        text='Upgrade host packages from the configured OS repositories. Kernel or service updates may require a restart; the portal will not restart the VM automatically.' if kind=='os' else 'Check for a release, review its changelog, then choose whether to install. Installed addons update with INSAP.'
        body='<form method="post" action="/admin/host" data-start-update>'+csrf+'<input type="hidden" name="update" value="'+kind+'"><div data-update-step="1"><p>'+text+'</p><footer><button type="button" data-tools-close>Cancel</button><button type="submit"'+(' disabled' if state.get('state')=='running' else '')+'>'+('Start OS update' if kind=='os' else 'Check for update')+'</button></footer></div></form>'
    return start+header+body+'</dialog>'
