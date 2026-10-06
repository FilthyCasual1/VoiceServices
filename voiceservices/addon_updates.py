"""Per-installed-addon release review with immutable upstream commit pins."""
import html,json,re
from urllib.request import urlopen
from .modules import CATALOG
E=lambda v:html.escape(str(v),quote=True)
def fetch(url,limit=2*1024**2):
    with urlopen(url,timeout=15) as response:
        raw=response.read(limit+1)
    if len(raw)>limit:raise ValueError('Addon release download is too large.')
    return raw
def settings(app):
    with app.store.connect() as db:row=db.execute("SELECT value FROM portal_settings WHERE key='addon_update_reviews'").fetchone()
    return json.loads(row[0]) if row else {}
def save(app,value):
    with app.store.connect() as db:db.execute("INSERT OR REPLACE INTO portal_settings VALUES('addon_update_reviews',?)",(json.dumps(value),))
def change(app,user,data):
    if user['role']!='admin':raise PermissionError('Administrator access required.')
    key=data.get('module','');action=data.get('action','')
    if key not in CATALOG or not app.modules.installed(key):raise ValueError('Choose an installed addon.')
    reviews=settings(app);previous=reviews.get(key,{})
    if action=='check-addon-update':
        try:
            commit=json.loads(fetch('https://api.github.com/repos/FilthyCasual1/VoiceServices/commits/main',1024*1024))['sha']
            if not re.fullmatch('[a-f0-9]{40}',commit):raise ValueError('Invalid release commit.')
            base='https://raw.githubusercontent.com/FilthyCasual1/VoiceServices/'+commit+'/'
            approved=json.loads(fetch(base+'voiceservices/addon_catalog.json'))[key]
            version=approved['version']
            if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('Invalid addon version.')
            installed=json.loads((app.modules.root/key/'manifest.json').read_text())['version']
            state='ready'
            if approved['api']!=app.modules.approved[key]['api'] or approved['sha256']!=app.modules.approved[key]['sha256']:state='core-required'
            elif tuple(map(int,version.split('.')))<=tuple(map(int,installed.split('.'))):state='current'
            elif version in previous.get('declined_versions',[]):state='declined'
            reviews[key]={'commit':commit,'version':version,'state':state,'changelog':fetch(base+'addon_sources/changelogs/'+key+'.md',262144).decode(),'declined_versions':previous.get('declined_versions',[])}
            save(app,reviews)
        except (OSError,KeyError,ValueError) as exc:raise ValueError('Unable to check addon release: '+str(exc)) from None
        return 'Addon release check complete.'
    review=previous
    if review.get('state')!='ready' or review.get('commit')!=data.get('release'):raise ValueError('Reload and review this addon release first.')
    if action=='decline-addon-update':
        review['state']='declined';review['declined_versions']=list(dict.fromkeys(review.get('declined_versions',[])+[review['version']]))
        save(app,reviews);return 'This addon version was declined.'
    if action=='install-addon-update':
        url='https://raw.githubusercontent.com/FilthyCasual1/VoiceServices/'+review['commit']+'/packages/addons/'+review['version']+'/'+key+'-'+review['version']+'.sraddon'
        try:raw=fetch(url)
        except OSError as exc:raise ValueError('Addon download failed: '+str(exc)) from None
        import io,zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:manifest=json.loads(archive.read('manifest.json'))
            if manifest['id']!=key or manifest['version']!=review['version']:raise ValueError('Package does not match the reviewed addon release.')
        except (KeyError,zipfile.BadZipFile):raise ValueError('Invalid addon release package.') from None
        app.modules.install(raw,replace=True);review['state']='installed';save(app,reviews)
        return 'Addon updated; saved settings and data retained.'
    raise ValueError('Unknown addon update action.')
def render(app,user,key):
    review=settings(app).get(key,{})
    hidden='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><input type="hidden" name="module" value="'+E(key)+'">'
    text='<form method="post" class="inline">'+hidden+'<button name="action" value="check-addon-update">Grab addon update</button></form>'
    if review.get('state')=='ready':
        text+='<div class="release-review"><p>Available addon version: '+E(review['version'])+'</p><details open><summary>Release changelog</summary><pre>'+E(review['changelog'])+'</pre></details><form method="post">'+hidden+'<input type="hidden" name="release" value="'+E(review['commit'])+'"><button name="action" value="install-addon-update">Proceed with addon update</button><button name="action" value="decline-addon-update">Decline this version</button></form></div>'
    elif review:
        messages={'current':'Addon is up to date.','declined':'This addon version was declined.','installed':'Addon update installed.','core-required':'This release changes addon code approved by the core. Update INSAP before installing it.'}
        text+='<p class="muted">'+E(messages.get(review.get('state'),'Check this addon again.'))+'</p>'
    return text

def install_from_repository(app,user,data):
    import io,zipfile
    if user['role']!='admin':raise PermissionError('Administrator access required.')
    key=data.get('module','')
    if key not in CATALOG or key not in app.modules.approved:raise ValueError('Choose an official addon.')
    if (app.modules.root/key).exists():raise ValueError('This addon is already present. Use its update controls or uninstall it first.')
    version=app.modules.approved[key]['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('Invalid approved addon version.')
    try:
        commit=json.loads(fetch('https://api.github.com/repos/FilthyCasual1/VoiceServices/commits/main',1024*1024))['sha']
        if not isinstance(commit,str) or not re.fullmatch('[a-f0-9]{40}',commit):raise ValueError('Invalid repository revision.')
        url='https://raw.githubusercontent.com/FilthyCasual1/VoiceServices/'+commit+'/packages/addons/'+version+'/'+key+'-'+version+'.sraddon'
        raw=fetch(url)
        import io,zipfile
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:manifest=json.loads(archive.read('manifest.json'))
        if not isinstance(manifest,dict) or manifest.get('id')!=key or manifest.get('version')!=version:raise ValueError('Repository package does not match the selected addon and portal release.')
        app.modules.install(raw)
    except (OSError,KeyError,TypeError,ValueError,zipfile.BadZipFile) as exc:
        raise ValueError('Repository installation failed: '+str(exc)+'. You can still upload a compatible package manually.') from None
    import time
    with app.store.connect() as db:db.execute('INSERT INTO audit(at,user_id,action) VALUES(?,?,?)',(int(time.time()),user['id'],'Installed repository addon '+key+' '+version+' at '+commit))
    return CATALOG[key][0]+' installed from the repository; version '+version+'.'

def repository_installer(app,user):
    from pathlib import Path
    from .version import __version__
    text='<details class="settings-section" id="addon-repository"><summary>Addon repository</summary><p>Browse official addons compatible with this INSAP release. Installed addons update automatically with INSAP; manual package installation remains available.</p><div class="download-grid">'
    for key,(title,description) in CATALOG.items():
        if key not in app.modules.approved:continue
        version=app.modules.approved[key]['version'];present=(app.modules.root/key).exists()
        text+='<article class="download-card"><span class="download-category">'+('Installed' if present else 'Available to install')+'</span><h4>'+E(title)+'</h4><p>'+E(description)+'</p><p class="download-meta">Version '+E(version)+' · API '+str(app.modules.approved[key]['api'])+'</p>'
        notes=Path(__file__).resolve().parents[1]/'addon_sources/changelogs'/(key+'.md')
        if not notes.is_file():notes=Path('/opt/serviceready/source/addon_sources/changelogs')/(key+'.md')
        if notes.is_file():text+='<details><summary>Release notes</summary><pre>'+E(notes.read_text()[:8192])+'</pre></details>'
        if not present:text+='<form method="post"><input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><input type="hidden" name="module" value="'+E(key)+'"><button name="action" value="install-repository-addon">Download and install</button></form>'
        else:text+='<p>Manage this installed addon below.</p>'
        text+='</article>'
    return text+'</div></details>'
