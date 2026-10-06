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
def record_revision(app,key,commit):
    path=app.modules.root/key/'manifest.json'
    manifest=json.loads(path.read_text());manifest['github_commit']=commit
    path.write_text(json.dumps(manifest,indent=2)+'\n')
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
        app.modules.install(raw,replace=True);record_revision(app,key,review['commit']);review['state']='installed';save(app,reviews)
        return 'Addon updated; saved settings and data retained.'
    raise ValueError('Unknown addon update action.')
def render(app,user,key):
    review=settings(app).get(key,{})
    hidden='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><input type="hidden" name="module" value="'+E(key)+'">'
    text='<form method="post" action="/admin" class="inline">'+hidden+'<button name="action" value="check-addon-update">Grab addon update</button></form>'
    if review.get('state')=='ready':
        text+='<div class="release-review"><p>Available addon version: '+E(review['version'])+'</p><details open><summary>Release changelog</summary><pre>'+E(review['changelog'])+'</pre></details><form method="post" action="/admin">'+hidden+'<input type="hidden" name="release" value="'+E(review['commit'])+'"><button name="action" value="install-addon-update">Proceed with addon update</button><button name="action" value="decline-addon-update">Decline this version</button></form></div>'
    elif review:
        messages={'current':'Addon is up to date.','declined':'This addon version was declined.','installed':'Addon update installed.','core-required':'This release changes addon code approved by the core. Update INSAP before installing it.'}
        text+='<p class="muted">'+E(messages.get(review.get('state'),'Check this addon again.'))+'</p>'
    return text

def install_from_repository(app,user,data,commit=None):
    import io,zipfile
    if user['role']!='admin':raise PermissionError('Administrator access required.')
    key=data.get('module','')
    if key not in CATALOG or key not in app.modules.approved:raise ValueError('Choose an official addon.')
    if (app.modules.root/key).exists():raise ValueError('This addon is already present. Use its update controls or uninstall it first.')
    version=app.modules.approved[key]['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('Invalid approved addon version.')
    try:
        if commit is None:commit=json.loads(fetch('https://api.github.com/repos/FilthyCasual1/VoiceServices/commits/main',1024*1024))['sha']
        if not isinstance(commit,str) or not re.fullmatch('[a-f0-9]{40}',commit):raise ValueError('Invalid repository revision.')
        url='https://raw.githubusercontent.com/FilthyCasual1/VoiceServices/'+commit+'/packages/addons/'+version+'/'+key+'-'+version+'.sraddon'
        raw=fetch(url)
        import io,zipfile
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:manifest=json.loads(archive.read('manifest.json'))
        if not isinstance(manifest,dict) or manifest.get('id')!=key or manifest.get('version')!=version:raise ValueError('Repository package does not match the selected addon and portal release.')
        app.modules.install(raw);record_revision(app,key,commit)
    except (OSError,KeyError,TypeError,ValueError,zipfile.BadZipFile) as exc:
        raise ValueError('Repository installation failed: '+str(exc)+'. You can still upload a compatible package manually.') from None
    import time
    with app.store.connect() as db:db.execute('INSERT INTO audit(at,user_id,action) VALUES(?,?,?)',(int(time.time()),user['id'],'Installed repository addon '+key+' '+version+' at '+commit))
    return CATALOG[key][0]+' installed from the repository; version '+version+'.'

def install_batch(app,user,data):
    if user['role']!='admin':raise PermissionError('Administrator access required.')
    keys=[key.removeprefix('install_module_') for key,value in data.items() if key.startswith('install_module_') and value=='yes']
    if not keys or any(key not in CATALOG or key not in app.modules.approved for key in keys):raise ValueError('Select one or more official addons.')
    try:
        commit=json.loads(fetch('https://api.github.com/repos/FilthyCasual1/VoiceServices/commits/main',1024*1024))['sha']
        if not isinstance(commit,str) or not re.fullmatch('[a-f0-9]{40}',commit):raise ValueError('Invalid repository revision.')
    except (OSError,KeyError,ValueError,TypeError) as exc:raise ValueError('Repository check failed: '+str(exc)+'. No addons were installed.') from None
    results=[]
    for key in keys:
        if (app.modules.root/key).exists():results.append(CATALOG[key][0]+': already present; skipped.');continue
        try:install_from_repository(app,user,{'module':key},commit);results.append(CATALOG[key][0]+': installed.')
        except ValueError as exc:results.append(CATALOG[key][0]+': failed — '+str(exc))
    return ' '.join(results)

def installed_table(app,user,rows):
    from .administration import OPTIONAL
    text='<table class="installed-addon-table"><tr><th>Item</th><th>Status / details</th><th>Actions</th></tr>';dialogs=''
    for title,status in rows:
        key=next(key for key,value in CATALOG.items() if value[0]==title)
        submenu=next((name for name,module in OPTIONAL.items() if module==key),None)
        text+='<tr><td>'+E(title)+'</td><td>'+E(status)+'</td><td class="addon-row-actions">'+('<a class="button" href="/admin/'+submenu+'">Configure addon…</a>' if submenu else '')+'<button type="button" data-dialog-open="manage-'+key+'">Update…</button><button type="button" data-dialog-open="remove-'+key+'">Uninstall…</button></td></tr>'
        dialogs+='<dialog id="manage-'+key+'" class="tools-wizard"><header><h3>'+E(title)+'</h3><button type="button" data-tools-close aria-label="Close">×</button></header><div class="wizard-progress"><p>'+E(CATALOG[key][1])+'</p>'+render(app,user,key)+'<button type="button" data-tools-close>Finish</button></div></dialog><dialog id="remove-'+key+'" class="tools-wizard"><header><h3>Uninstall '+E(title)+'</h3><button type="button" data-tools-close aria-label="Close">×</button></header><div class="wizard-progress"><form action="/admin" method="post"><input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><input type="hidden" name="module" value="'+key+'"><p>Removes the addon files; saved data is retained.</p><button name="action" value="remove">Uninstall package</button></form><button type="button" data-tools-close>Cancel</button></div></dialog>'
    return text+'</table>'+dialogs

def repository_installer(app,user,result=""):
    from pathlib import Path
    try:notes_catalog=json.loads(Path(__file__).with_name('addon_notes.json').read_text())
    except (OSError,ValueError):notes_catalog={}
    if not isinstance(notes_catalog,dict):notes_catalog={}
    text='<button type="button" data-dialog-open="install-addon">Install addon…</button><dialog id="install-addon" class="tools-wizard addon-config-wizard"><header><h3>Addon repository and installation</h3><button type="button" data-tools-close aria-label="Close">×</button></header><ol class="tools-steps"><li>Source</li><li>Choose</li><li>Review</li></ol><section data-install-step="0"'+(' hidden' if result else '')+'><h3>Choose an installation source</h3><p>Official packages are checked for compatibility with this portal release. Installed addons update with INSAP.</p><footer><button type="button" data-tools-close>Cancel</button><button type="button" data-install-next="1">Browse addon repository →</button><button type="button" data-install-next="manual">Manual installation →</button></footer></section><section data-install-step="1" hidden><h3>Addon repository</h3><p data-install-selection-error class="notice error" hidden role="alert"></p><div class="download-grid">'
    count=0
    for key,(title,description) in CATALOG.items():
        if key not in app.modules.approved or (app.modules.root/key).exists():continue
        count+=1;version=app.modules.approved[key]['version']
        text+='<article class="download-card"><span class="download-category">Available to install</span><h4>'+E(title)+'</h4><p>'+E(description)+'</p><p class="download-meta">Version '+E(version)+' · API '+str(app.modules.approved[key]['api'])+'</p>'
        notes=notes_catalog.get(key,'')
        if isinstance(notes,str) and notes:text+='<details><summary>Release notes</summary><pre>'+E(notes[:8192])+'</pre></details>'
        else:text+='<p class="muted">Release notes are unavailable. Installation controls remain available.</p>'
        text+='<label class="tools-choice"><input type="checkbox" data-repository-addon="'+key+'" data-addon-title="'+E(title)+'" data-addon-version="'+E(version)+'"> Select addon</label></article>'
    if not count:text+='<p>All official addons are already installed.</p>'
    text+='</div><footer><button type="button" data-install-next="0">← Back</button><button type="button" data-install-next="2">Review selected addons →</button></footer></section><section data-install-step="2" hidden><h3>Review installation</h3><p data-install-review></p><p>The package is downloaded from the approved repository and validated before installation. It adds executable addon files.</p><form method="post" action="/admin" data-addon-install><input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><div data-install-modules></div><footer><button type="button" data-install-next="1">← Back</button><button name="action" value="install-repository-addons">Download and install selected</button></footer></form></section><section data-install-step="manual" hidden><h3>Manual installation</h3><form action="/admin/addons/upload" method="post" enctype="multipart/form-data"><input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><label>Addon package (.sraddon)</label><input type="file" name="file" accept=".sraddon" required><p>Only packages with code approved for this portal release can be installed.</p><footer><button type="button" data-install-next="0">← Back</button><button>Install package</button></footer></form></section></dialog>'
    if result:text=text.replace('</dialog>','<section data-install-step="result"><h3>Installation results</h3><p>'+E(result)+'</p><button type="button" data-install-next="0">Install more addons</button><button type="button" data-tools-close>Finish</button></section></dialog>')
    return text
