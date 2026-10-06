"""Local administrator controls for host networking, time and uploaded-data storage."""
import html,json,time
E=lambda v:html.escape(str(v),quote=True)
def change(app,user,data):
 if user['role']!='admin':raise PermissionError('Administrator access required.')
 if not app.store.accounts:raise ValueError('Connect a supported Linux host provider first.')
 if not app.base.startswith('https://') or not app.secure:raise ValueError('HTTPS and secure cookies are required.')
 from . import external_auth
 if external_auth.identity(app,user):raise ValueError('Use a local administrator account for host changes.')
 payload={key:data.get(key,'') for key in ('kind','raid_mode','operation','disk','fingerprint','confirm','erase_confirm','connection','mode','address','gateway','dns','hostname','servers','timezone','ipv6_mode','ipv6_address','ipv6_gateway','ipv6_dns')}
 if data.get('kind')=='storage-raid':
  payload['members']=[{'disk':data[key],'fingerprint':data.get('raid_fingerprint_'+key.removeprefix('raid_disk_'),'')} for key in sorted(data) if key.startswith('raid_disk_') and data[key]]
 app.store.accounts.call('host-confirm' if data.get('kind')=='confirm-network' else 'host-start',user['username'],data.get('current_password',''),json.dumps(payload))
 with app.store.connect() as db:db.execute('INSERT INTO audit(at,user_id,action) VALUES(?,?,?)',(int(time.time()),user['id'],'Host configuration: '+data.get('kind','')))
 return 'Host operation accepted. Refresh this page to see progress.'
def render(app,user,section):
 if not app.store.accounts:return '<p class="notice">Host controls require a connected Linux account broker.</p>'
 try:state=app.store.accounts.call('host-status','','',section)
 except ValueError as exc:return '<p class="notice error">'+E(exc)+'</p><p>Use <a href="/admin/system-updates">Portal and host updates</a> to install the current host integration, then retry this page.</p>'
 if state.get('provider')=='openwrt':return '<p class="notice">'+E(state['provider_message'])+'</p>'
 job=state['job']
 text='<p class="notice">'+E(job['state'])+': '+E(job['message'])+'</p><p><a href="/admin/'+section+'">Refresh status</a></p>'
 text+=''.join('<p class="notice error">'+E(error)+'</p>' for error in state.get('errors',[]))
 csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
 def form(kind,body,label):return '<form method="post" class="panel">'+csrf+'<input type="hidden" name="kind" value="'+kind+'">'+body+'<label>Local administrator password</label><input type="password" name="current_password" autocomplete="current-password" required><button>'+label+'</button></form>'
 if section=='storage':
  if state['storage']!='Not configured' and not state['storage_available']:text+='<p class="notice error">Storage disk missing. Core services remain available; uploaded content is blocked. Reattach the original volume or configure a blank replacement below. A replacement does not recover files from the missing disk.</p>'
  text+='<p>Storage volume: '+E(state['storage'])+'</p><p>A separate disk stores downloads, update packages and PXE images. Unused, unpartitioned disks can be erased and configured, and the current upload disk can be reformatted even when it contains files. Formatting is permanent. Accounts and application settings remain on the boot disk.</p>'
  if state.get('raid'):text+='<h3>'+E(state['raid'])+'</h3><pre>'+E(state.get('raid_status','Unavailable'))+'</pre>'
  from . import disk_health
  text+=disk_health.render(app,state)
  if state['storage_available'] and state.get('vm_provider'):text+='<p class="notice">Virtual machine detected ('+E(state['vm_provider'])+'). TRIM and defragmentation are disabled for this host.</p>'
  if state['storage_available'] and not state.get('vm_provider'):text+=form('storage-maintenance','<h3>Storage maintenance</h3><label>Task</label><select name="operation"><option value="trim">TRIM unused space (when supported)</option><option value="defrag">Check fragmentation; defragment if needed</option></select><p>Only the upload volume is targeted. Virtual disks may not expose discard/TRIM support.</p>','Run disk maintenance')
  eligible=[d for d in state['disks'] if d.get('raid_eligible',d['eligible'])][:8]
  text+='<h3>Software RAID</h3>'
  if state['storage_available']:text+='<p class="notice">Upload storage is already mounted. To create a replacement array, first detach the existing data volume. Existing files are not migrated from a detached volume.</p>'
  elif len(eligible)<2:text+='<p class="notice">Attach at least two unused, unpartitioned data disks to create a mirrored (RAID 1) or combined-capacity (RAID 0) volume. Boot disks, partitioned disks and mounted disks cannot be selected.</p>'
  if len(eligible)>=2 and not state['storage_available']:
   choices=''.join('<label><input type="checkbox" name="raid_disk_'+str(index)+'" value="'+E(d['path'])+'"> '+E(d['path'])+' · '+E(d.get('model') or 'Disk')+' · '+str(round(d['size']/1024**3,1))+' GiB</label><input type="hidden" name="raid_fingerprint_'+str(index)+'" value="'+E(d['fingerprint'])+'">' for index,d in enumerate(eligible))
   text+='<div class="storage-raid-controls">'+form('storage-raid','<label>Storage mode</label><select name="raid_mode"><option value="mirror">Mirror (RAID 1): duplicate copies</option><option value="stripe">Combined capacity (RAID 0): more storage</option></select><p class="notice error">Combined capacity has no redundancy: failure of any member loses the entire volume.</p><p>RAID 1 stores a copy on every selected disk and continues working if a member fails. Usable capacity is approximately the smallest selected disk. A mirror is not a backup. All selected disks will be erased; existing upload storage must be detached first.</p>'+choices+'<label><input type="checkbox" name="erase_confirm" value="yes" required> Erase the selected disks and create an array</label><label>Type CREATE ARRAY</label><input name="confirm" required>','Create storage array')+'</div>'
  for d in state['disks']:
   text+='<div class="panel"><strong>'+E(d['path'])+'</strong> — '+E(d.get('model') or 'Disk')+' — '+str(round(d['size']/1024**3,1))+' GiB '+(' (available)' if d['eligible'] else ' (in use or contains data)')+'</div>'
   if d.get('raid_eligible',d['eligible']) and not state['storage_available']:text+=form('storage','<input type="hidden" name="disk" value="'+E(d['path'])+'"><input type="hidden" name="fingerprint" value="'+E(d['fingerprint'])+'"><label><input type="checkbox" name="erase_confirm" value="yes" required> Erase all data on this disk</label><label>Type FORMAT '+E(d['path'])+' to erase this disk</label><input name="confirm" required>','Format and use disk')
   if d.get('reformat'):text+='<div class="storage-format-controls"><h3>Reformat current upload disk</h3>'+form('storage-reset','<input type="hidden" name="disk" value="'+E(d['path'])+'"><input type="hidden" name="fingerprint" value="'+E(d['fingerprint'])+'"><p class="notice error">All uploaded downloads, update packages, PXE images, custom branding images and profile pictures on this disk will be permanently erased. Accounts, settings, categories and external download links are retained. The portal will briefly disconnect.</p><label><input type="checkbox" name="erase_confirm" value="yes" required> I understand that all uploaded data will be erased</label><label>Type ERASE '+E(d['path'])+'</label><input name="confirm" required>','Erase and reformat data disk')+'</div>'
 else:
  text+='<p>Current hostname: '+E(state['hostname'])+'</p><pre>'+E(state['connections'])+'</pre><pre>'+E(state['time'])+'</pre>'
  options=''.join('<option value="'+E(line.split(':')[1])+'">'+E(line)+'</option>' for line in state['connections'].splitlines() if len(line.split(':'))>=3 and line.rsplit(':',1)[-1]!='lo')
  text+=form('network','<h3>IP configuration</h3><label>Active connection</label><select name="connection">'+options+'</select><label>Address method</label><select name="mode"><option value="keep">Keep existing settings</option><option value="auto">DHCP</option><option value="manual">Static</option><option value="disabled">Disabled (IPv6 only)</option></select><label>Static address / prefix</label><input name="address" placeholder="192.168.1.20/24"><label>Static gateway</label><input name="gateway"><label>DNS servers (space separated; blank uses DHCP)</label><input name="dns"><label>Hostname (blank retains current host setting)</label><input name="hostname"><h4>IPv6</h4><label>Address method</label><select name="ipv6_mode"><option value="">Keep existing settings</option><option value="auto">Automatic (router advertisements / SLAAC)</option><option value="dhcp">DHCPv6</option><option value="manual">Static</option><option value="disabled">Disabled</option></select><label>Static IPv6 address / prefix</label><input name="ipv6_address" placeholder="2001:db8::20/64"><label>IPv6 gateway (optional)</label><input name="ipv6_gateway"><label>IPv6 DNS servers (space separated)</label><input name="ipv6_dns"><p>Confirm at the new address within 90 seconds, otherwise the previous connection is restored.</p>','Apply network settings')
  if job['state']=='pending':text+=form('confirm-network','<p>Confirm that this connection works.</p>','Keep network settings')
  from . import regional
  text+=form('timezone','<h3>Host time zone</h3><label>Time zone</label>'+regional.timezone_select('timezone',state.get('timezone') if state.get('timezone') not in (None,'Unavailable') else regional.settings(app)['timezone']),'Save time zone')
  text+=form('ntp','<h3>Time synchronization</h3><label>NTP servers (space separated)</label><input name="servers" required placeholder="time.example.net">','Save NTP servers')
 return text
