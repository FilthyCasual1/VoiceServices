"""Administrator delivery of private portal notifications."""
import html,time
E=lambda v:html.escape(str(v),quote=True)
def change(app,user,data):
    if user['role']!='admin': raise PermissionError('Administrator access required.')
    title=data.get('title','').strip();body=data.get('body','').strip();recipient=data.get('recipient','')
    if not 1<=len(title)<=120 or not 1<=len(body)<=5000: raise ValueError('Enter a subject and message (up to 120 and 5000 characters).')
    priority=data.get('priority','info')
    if priority not in ('info','caution','urgent'): raise ValueError('Choose Info, Caution or Urgent priority.')
    with app.store.connect() as db:
        if recipient=='all': recipients=db.execute('SELECT id FROM users').fetchall()
        else:
            try: key=int(recipient)
            except ValueError: raise ValueError('Choose a recipient.')
            recipients=db.execute('SELECT id FROM users WHERE id=?',(key,)).fetchall()
        if not recipients: raise ValueError('Recipient unavailable.')
        db.executemany('INSERT INTO notifications(user_id,title,body,created,sender,priority) VALUES(?,?,?,?,?,?)',[(r['id'],title,body,int(time.time()),user['display_name'] or user['username'],priority) for r in recipients])
    return 'Notification sent to '+str(len(recipients))+' account(s).'
def render(app,user):
    with app.store.connect() as db: users=db.execute('SELECT id,username,display_name FROM users ORDER BY username').fetchall()
    options='<option value="">Choose a recipient</option><option value="all">All accounts</option>'+''.join('<option value="'+str(r['id'])+'">'+E(r['username'])+(' — '+E(r['display_name']) if r['display_name'] else '')+'</option>' for r in users)
    return '<p>Send an internal system notice to one account or all accounts. Notifications are delivered to the portal inbox.</p><div class="panel"><form method="post"><input type="hidden" name="csrf" value="'+E(user['csrf'])+'"><label>Recipient</label><select name="recipient" required>'+options+'</select><label>Priority</label><select name="priority"><option value="info">Info</option><option value="caution">Caution</option><option value="urgent">Urgent</option></select><label>Subject</label><input name="title" maxlength="120" required><label>Message</label><textarea name="body" rows="6" maxlength="5000" required></textarea><br><button>Send notification</button></form></div>'
