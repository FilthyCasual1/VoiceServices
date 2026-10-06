"""Local administrator controls for host networking, time and uploaded-data storage."""
import html,json,time
E=lambda v:html.escape(str(v),quote=True)
def change(app,user,data):
 if user['role']!='admin':raise PermissionError('Administrator access required.')
 if not app.store.accounts:raise ValueError('Connect a supported Linux host provider first.')
 if not app.base.startswith('https://') or not app.secure:raise ValueError('HTTPS and secure cookies are required.')
 from . import external_auth
 if external_auth.identity(app,user):raise ValueError('Use a local administrator account for host changes.')
 payload={key:data.get(key,'') for key in ('kind','operation','disk','fingerprint','confirm','connection','mode','address','gateway','dns','hostname','servers')}
 app.store.accounts.call('host-confirm' if data.get('kind')=='confirm-network' else 'host-start',user['username'],data.get('current_password',''),json.dumps(payload))
 with app.store.connect() as db:db.execute('INSERT INTO audit(at,user_id,action) VALUES(?,?,?)',(int(time.time()),user['id'],'Host configuration: '+data.get('kind','')))
 return 'Host operation accepted. Refresh this page to see progress.'
def render(app,user,section):
 if not app.store.accounts:return '<p class="notice">Host controls require a connected Linux account broker.</p>'
 try:state=app.store.accounts.call('host-status','','',section)
 except ValueError as exc:return '<p class="notice error">'+E(exc)+'</p><p>Use <a href="/admin/system-updates">Portal and host updates</a> to install the current host integration, then retry this page.</p>'
 job=state['job']
 text='<p class="notice">'+E(job['state'])+': '+E(job['message'])+'</p><p><a href="/admin/'+section+'">Refresh status</a></p>'
 text+=''.join('<p class="notice error">'+E(error)+'</p>' for error in state.get('errors',[]))
 csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
 def form(kind,body,label):return '<form method="post" class="panel">'+csrf+'<input type="hidden" name="kind" value="'+kind+'">'+body+'<label>Local administrator password</label><input type="password" name="current_password" autocomplete="current-password" required><button>'+label+'</button></form>'
 if section=='storage':
  if state['storage']!='Not configured' and not state['storage_available']:text+='<p class="notice error">Upload disk missing. Core services remain available; uploaded content is blocked. Reattach the original volume or configure a blank replacement below. A replacement does not recover files from the missing disk.</p>'
  text+='<p>Upload volume: '+E(state['storage'])+'</p><p>A separate disk stores downloads, update packages and PXE images. Only blank, unused disks can be formatted. Formatting is permanent. Existing repositories are moved; account and application metadata remain on the boot disk.</p>'
  for d in state['disks']:
   text+='<div class="panel"><strong>'+E(d['path'])+'</strong> — '+E(d.get('model') or 'Disk')+' — '+str(round(d['size']/1024**3,1))+' GiB '+(' (available)' if d['eligible'] else ' (in use or contains data)')+'</div>'
   if d['eligible'] and not state['storage_available']:text+=form('storage','<input type="hidden" name="disk" value="'+E(d['path'])+'"><input type="hidden" name="fingerprint" value="'+E(d['fingerprint'])+'"><label>Type FORMAT '+E(d['path'])+' to erase this disk</label><input name="confirm" required>','Format and use disk')
 else:
  text+='<p>Current hostname: '+E(state['hostname'])+'</p><pre>'+E(state['connections'])+'</pre><pre>'+E(state['time'])+'</pre>'
  options=''.join('<option value="'+E(line.split(':')[1])+'">'+E(line)+'</option>' for line in state['connections'].splitlines() if len(line.split(':'))>=3)
  text+=form('network','<h3>IPv4 configuration</h3><label>Active connection</label><select name="connection">'+options+'</select><label>Address method</label><select name="mode"><option value="auto">DHCP</option><option value="manual">Static</option></select><label>Static address / prefix</label><input name="address" placeholder="192.168.1.20/24"><label>Static gateway</label><input name="gateway"><label>DNS servers (space separated; blank uses DHCP)</label><input name="dns"><label>Hostname (blank retains current host setting)</label><input name="hostname"><p>Confirm at the new address within 90 seconds, otherwise the previous connection is restored.</p>','Apply network settings')
  if job['state']=='pending':text+=form('confirm-network','<p>Confirm that this connection works.</p>','Keep network settings')
  text+=form('ntp','<h3>Time synchronization</h3><label>NTP servers (space separated)</label><input name="servers" required placeholder="time.example.net">','Save NTP servers')
 return text
