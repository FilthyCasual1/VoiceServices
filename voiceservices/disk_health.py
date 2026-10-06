"""Display upload disk health and deduplicate administrator health notifications."""
import html,json,time
E=lambda v:html.escape(str(v),quote=True)
def render(app,state):
 disks=state.get('smart',[])
 if not isinstance(disks,list) or not disks:return ''
 text='<h3>Upload disk SMART health</h3><table><tr><th>Disk</th><th>Health</th><th>Details</th></tr>'
 with app.store.connect() as db:
  for disk in disks:
   health=disk.get('state','Unavailable');message=disk.get('message','');detail=message
   if disk.get('temperature') is not None:detail+=' · '+str(disk['temperature'])+' °C'
   if disk.get('hours') is not None:detail+=' · '+str(disk['hours'])+' power-on hours'
   text+='<tr><td>'+E(disk.get('disk',''))+'</td><td>'+E(health)+'</td><td>'+E(detail)+'</td></tr>'
   key='smart-alert:'+disk.get('identity',disk.get('disk',''));previous=db.execute('SELECT value FROM portal_settings WHERE key=?',(key,)).fetchone()
   if health in ('Caution','Failed') and (not previous or json.loads(previous[0])!=health):
    for user in db.execute("SELECT id FROM users WHERE role='admin'").fetchall():db.execute('INSERT INTO notifications(user_id,title,body,created,priority) VALUES(?,?,?,?,?)',(user['id'],'Upload disk '+health.lower(),disk.get('disk','')+': '+message,int(time.time()),'urgent' if health=='Failed' else 'caution'))
   db.execute('INSERT OR REPLACE INTO portal_settings VALUES(?,?)',(key,json.dumps(health)))
 return text+'</table><p class="muted">SMART readings are cached for up to 60 seconds. Many virtual disks do not expose physical SMART data.</p>'
