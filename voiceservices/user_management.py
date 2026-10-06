"""Administrator account lifecycle with last-administrator protection."""
import html,re,sqlite3
E=lambda value:html.escape(str(value),quote=True)
def change(app,actor,data):
    if actor['role']!='admin': raise PermissionError('Administrator access required.')
    action=data.get('action')
    if action in ('invite-create','invite-revoke'):
        from .onboarding import invitation_action
        return invitation_action(app,actor,data)
    if action=='create':
        name=data.get('username','').strip()
        if not re.fullmatch(r'[A-Za-z0-9_.-]{3,64}',name): raise ValueError('Use 3–64 letters, digits, dots, underscores or hyphens for a username.')
        if data.get('password')!=data.get('confirm_password'): raise ValueError('Passwords do not match.')
        try: app.store.create_user(name,data.get('password',''),data.get('role','user'))
        except sqlite3.IntegrityError: raise ValueError('Username already exists.') from None
        name_label=data.get('display_name','').strip()[:100]
        with app.store.connect() as db: db.execute('UPDATE users SET display_name=? WHERE username=?',(name_label,name))
        return 'User created.'
    if action not in ('delete','role'): raise ValueError('Unknown user action.')
    try: identifier=int(data.get('user',''))
    except ValueError: raise ValueError('Select a user.')
    with app.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        target=db.execute('SELECT * FROM users WHERE id=?',(identifier,)).fetchone()
        if not target: raise ValueError('User not found.')
        if identifier==actor['id']: raise ValueError('Use My Account for your own account; you cannot delete or change your own role here.')
        if target['role']=='admin' and db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]<=1: raise ValueError('The last administrator cannot be removed or demoted.')
        if target['password']=='external':
            if action=='role': raise ValueError('External identities cannot become local administrators.')
            if data.get('confirm')!='yes': raise ValueError('Confirm removal of portal access.')
            db.execute('UPDATE external_identities SET active=0 WHERE user_id=?',(identifier,))
            db.execute('DELETE FROM sessions WHERE user_id=?',(identifier,))
            db.execute('DELETE FROM phones WHERE user_id=?',(identifier,))
            db.execute("INSERT INTO audit(at,user_id,action) VALUES(strftime('%s','now'),?,?)",(actor['id'],'Disabled external access '+target['username']))
            return 'External portal access disabled; the remote account is unchanged.'
        if action=='role':
            role=data.get('role','')
            if role not in ('user','admin'): raise ValueError('Choose a valid portal role.')
            db.execute('UPDATE users SET role=? WHERE id=?',(role,identifier))
            db.execute('DELETE FROM sessions WHERE user_id=?',(identifier,))
            db.execute('DELETE FROM phones WHERE user_id=?',(identifier,))
            return 'Role changed; existing sessions revoked.'
        if data.get('confirm')!='yes': raise ValueError('Confirm deletion of this account.')
        if app.store.accounts: app.store.accounts.call('delete',target['username'],'')
        for table,column in [('sessions','user_id'),('phones','user_id'),('contacts','owner')]: db.execute('DELETE FROM '+table+' WHERE '+column+'=?',(identifier,))
        db.execute('DELETE FROM users WHERE id=?',(identifier,))
        db.execute('INSERT INTO audit(at,user_id,action) VALUES(strftime(\'%s\',\'now\'),?,?)',(actor['id'],'Deleted user '+target['username']))
    return 'User deleted; sessions, application bindings and personal contacts removed.'

def render(app,actor):
    csrf='<input type="hidden" name="csrf" value="'+E(actor['csrf'])+'">'
    backend='Linux system accounts' if app.store.accounts else 'Local portal accounts'
    content='<p>Authentication: <strong>'+backend+'</strong>. <a href="/account">Change your password</a>.</p><table class="users-table"><tr><th>Username</th><th>Portal access</th><th>Actions</th></tr>'
    with app.store.connect() as db:
        for row in db.execute('SELECT id,username,role FROM users ORDER BY username'):
            external=db.execute('SELECT provider,active FROM external_identities WHERE user_id=?',(row['id'],)).fetchone()
            content+='<tr><td>'+E(row['username'])+'</td><td>'+E(row['role'])+(' · '+E(external['provider'])+(' (disabled)' if not external['active'] else '') if external else '')+'</td><td>'
            if row['id']==actor['id']: content+='Signed-in account'
            else:
                hidden=csrf+'<input type="hidden" name="user" value="'+str(row['id'])+'">'
                content+='<form method="post" class="user-action">'+hidden+'<select name="role"><option value="user">User</option><option value="admin"'+(' selected' if row['role']=='admin' else '')+'>Administrator</option></select><button name="action" value="role">Save role</button></form><form method="post" class="user-action">'+hidden+'<label class="inline"><input type="checkbox" name="confirm" value="yes" required> Confirm deletion</label><button name="action" value="delete">Delete user</button></form>'
            content+='</td></tr>'
    content+='</table><h2>Create a user</h2><div class="panel"><form method="post">'+csrf+'<input name="action" type="hidden" value="create"><label>Username</label><input name="username" autocomplete="off" required><label>Display name (optional)</label><input name="display_name" maxlength="100"><label>Password</label><input name="password" type="password" minlength="12" autocomplete="new-password" required><label>Confirm password</label><input name="confirm_password" type="password" minlength="12" autocomplete="new-password" required><label>Portal role</label><select name="role"><option value="user">User</option><option value="admin">Administrator</option></select><br><button>Create user</button></form></div>'
    content+='<p>Deletion removes personal portal data and revokes sessions. On Linux it also deletes the enrolled system account, preserving its home directory. Portal administrator roles do not grant operating-system administrator privileges.</p>'
    from .onboarding import invitations
    return invitations(app,actor)+content
