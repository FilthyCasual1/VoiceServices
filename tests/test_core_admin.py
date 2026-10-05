import unittest,socket
from unittest.mock import patch
import test_app
from voiceservices import user_management
class CoreAdminTests(unittest.TestCase):
    setUp=test_app.PortalTests.setUp
    tearDown=test_app.PortalTests.tearDown
    request=test_app.PortalTests.request
    user=test_app.PortalTests.user
    def test_branding_and_block_editor_escape_and_persist(self):
        token,user=self.user('admin')
        response=self.request('/admin/branding','POST',{'csrf':user['csrf'],'title':'Example & Co','subtitle':'Custom portal'},token)
        self.assertEqual(response['status'],'200 OK')
        self.assertIn('Example &amp; Co',self.request()['body'])
        self.assertIn(socket.gethostname(),self.request()['body'])
        response=self.request('/admin/home','POST',{'csrf':user['csrf'],'title':'Help','body':'Contact <script>alert(1)</script>','url':'/login','position':'1','enabled':'yes'},token)
        self.assertEqual(response['status'],'200 OK')
        body=self.request()['body'];self.assertIn('&lt;script&gt;',body);self.assertNotIn('<script>',body)
        self.assertLess(body.index('<h2>Help'),body.index('<h2>1. Get an account'))
        response=self.request('/admin/home','POST',{'csrf':user['csrf'],'title':'Bad','body':'x','url':'javascript:alert(1)','enabled':'yes'},token)
        self.assertEqual(response['status'],'400 Bad Request')
        with self.app.store.connect() as db: key=db.execute("SELECT id FROM home_blocks WHERE title='Help'").fetchone()[0]
        self.request('/admin/home','POST',{'csrf':user['csrf'],'action':'delete','block':str(key)},token)
        self.assertNotIn('<h2>Help',self.request()['body'])
        self.assertEqual(self.request('/admin/branding',token=self.user('alice')[0])['status'],'403 Forbidden')
    def test_create_delete_roles_and_revoke_user_data(self):
        token,admin=self.user('admin')
        response=self.request('/admin/users','POST',{'csrf':admin['csrf'],'action':'create','username':'charlie','display_name':'Charlie','password':'long-password-charlie','confirm_password':'long-password-charlie','role':'user'},token)
        self.assertEqual(response['status'],'200 OK')
        child=self.app.store.login('charlie','long-password-charlie');person=self.app.store.session(child)
        self.app.store.add_contact(person,'Personal','123');binding=self.app.store.bind_phone(person,'SEP112233445566')
        self.assertIn('Hello, Charlie.',self.request(token=child)['body'])
        self.assertNotIn('Current user:',self.request(token=child)['body'])
        self.assertIn('Administrator',self.request(token=token)['body'])
        self.assertEqual(self.request('/admin/users','POST',{'csrf':admin['csrf'],'action':'delete','user':str(admin['id']),'confirm':'yes'},token)['status'],'400 Bad Request')
        self.assertEqual(self.request('/admin/users','POST',{'csrf':admin['csrf'],'action':'delete','user':str(person['id'])},token)['status'],'400 Bad Request')
        self.assertEqual(self.request('/admin/users','POST',{'csrf':admin['csrf'],'action':'delete','user':str(person['id']),'confirm':'yes'},token)['status'],'200 OK')
        self.assertIsNone(self.app.store.session(child));self.assertIsNone(self.app.store.phone_user(binding))
        self.assertIsNone(self.app.store.login('charlie','long-password-charlie'))
        with self.assertRaises(ValueError): user_management.change(self.app,{'id':999,'role':'admin'},{'action':'delete','user':str(admin['id']),'confirm':'yes'})
    def test_display_name_and_portal_wide_overview(self):
        token,user=self.user('alice')
        self.request('/account','POST',{'csrf':user['csrf'],'action':'profile','display_name':'Alice <Example>'},token)
        self.assertIn('Hello, Alice &lt;Example&gt;.',self.request(token=token)['body'])
        token,_=self.user('admin');body=self.request('/admin',token=token)['body']
        for item in ('Accounts','Host memory','Active portal sessions','Downloads','Voice Services','Data disk','Installed addons'): self.assertIn(item,body)
        self.assertNotIn('Open application',body)
    def test_broker_delete_is_enrolled_only(self):
        import test_account_broker
        broker=test_account_broker.broker
        with patch.object(broker,'eligible',return_value=False),patch.object(broker.subprocess,'run') as run:
            with self.assertRaises(ValueError): broker.handle({'action':'delete','username':'admin','password':''})
            run.assert_not_called()
        with patch.object(broker,'eligible',return_value=True),patch.object(broker.subprocess,'run') as run:
            broker.handle({'action':'delete','username':'alice','password':''})
            self.assertEqual(run.call_args.args[0],['/usr/sbin/deluser','alice'])
    def test_logo_rejects_svg_and_serves_png(self):
        import base64
        from voiceservices import branding
        with self.assertRaises(ValueError): branding.upload_logo(self.app,b'<svg onload="alert(1)"></svg>')
        image=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aB9sAAAAASUVORK5CYII=')
        branding.upload_logo(self.app,image)
        response={}
        def start(status,headers): response.update(status=status,headers=dict(headers))
        data=b''.join(self.app({'PATH_INFO':'/branding/logo','REQUEST_METHOD':'GET'},start))
        self.assertEqual(data,image);self.assertEqual(response['headers']['Content-Type'],'image/png')
        self.assertIn('src="/branding/logo"',self.request()['body'])
    def test_account_profile_and_other_session_revocation(self):
        token,user=self.user('alice');other=self.app.store.login('alice','a-long-password')
        response=self.request('/account','POST',{'csrf':user['csrf'],'action':'profile','display_name':'Alice','email':'alice@example.local','phone':'+1 555 0100','timezone':'America/Chicago'},token)
        self.assertEqual(response['status'],'200 OK')
        for value in ('Your profile','Linked services','alice@example.local','America/Chicago'): self.assertIn(value,response['body'])
        self.request('/account','POST',{'csrf':user['csrf'],'action':'revoke-sessions'},token)
        self.assertIsNone(self.app.store.session(other));self.assertIsNotNone(self.app.store.session(token))
    def test_crystalblue_brand_attribution_and_block_legend(self):
        body=self.request()['body']
        self.assertIn('<strong>CasualNetworks</strong>',body)
        self.assertIn('<footer>CasualNetworks Service Ready',body)
        from voiceservices.version import __version__,__codename__
        self.assertIn(__version__+' '+__codename__,body)
        token,user=self.user('admin')
        legend=self.request('/admin/home',token=token)['body']
        for phrase in ('Page links legend','/create-account','/account','/my-phone'): self.assertIn(phrase,legend)
        self.request('/admin/branding','POST',{'csrf':user['csrf'],'title':'Example Network','subtitle':'My services'},token)
        body=self.request()['body'];self.assertIn('<strong>Example Network</strong>',body)
        self.assertIn('<footer>Example Network | Powered By CasualNetworks ServiceReady',body)

    def test_overview_hides_uninstalled_addons(self):
        token,_=self.user('admin')
        for key in self.app.modules.approved: self.app.modules.change(key,False)
        body=self.request('/admin',token=token)['body']
        self.assertIn('No addons installed.',body)
        self.assertNotIn('Package absent',body)
        self.assertNotIn('<td>Voice Services</td>',body)
        from addon_support import install
        install(self.app,'downloads')
        body=self.request('/admin',token=token)['body']
        self.assertIn('<td>Downloads</td>',body)
        self.assertNotIn('<td>ESXi Management</td>',body)

    def test_custom_masthead_asset_and_reset(self):
        from voiceservices import branding
        image=b'\xff\xd8\xffexample\xff\xd9'
        branding.upload_logo(self.app,image,'masthead')
        self.assertEqual(branding.logo(self.app,'masthead')[0],image)
        self.assertIsNotNone(branding.logo(self.app,'masthead'))
        token,user=self.user('admin')
        page=self.request('/admin/branding',token=token)['body']
        self.assertIn('/admin/branding/masthead/upload',page)
        self.request('/admin/branding','POST',{'csrf':user['csrf'],'title':'CasualNetworks','subtitle':'ServiceReady INSAP','reset_masthead':'yes'},token)
        self.assertIsNone(branding.logo(self.app,'masthead'))
        response={}
        def start(status,headers): response['status']=status
        asset=b''.join(self.app({'PATH_INFO':'/branding/masthead','REQUEST_METHOD':'GET'},start))
        self.assertEqual(response['status'],'200 OK')
        self.assertTrue(asset.startswith(b'\x89PNG'))

    def test_masthead_layout_selection(self):
        token,user=self.user('admin')
        self.assertIn('class="masthead-wide"',self.request()['body'])
        data={'csrf':user['csrf'],'title':'CasualNetworks','subtitle':'ServiceReady INSAP','masthead_layout':'compact'}
        self.assertEqual(self.request('/admin/branding','POST',data,token)['status'],'200 OK')
        body=self.request()['body']
        self.assertIn('class="masthead-compact"',body)
        self.assertIn('class="masthead-image"',body)
        data['masthead_layout']='wide';self.request('/admin/branding','POST',data,token)
        self.assertNotIn('class="masthead-image"',self.request()['body'])
        data['masthead_layout']='invalid'
        self.assertEqual(self.request('/admin/branding','POST',data,token)['status'],'400 Bad Request')

    def test_navigation_and_login_errors_use_portal_shell(self):
        import io
        response={}
        def start(status,headers): response.update(status=status)
        body=b''.join(self.app({'PATH_INFO':'/login','REQUEST_METHOD':'POST','CONTENT_LENGTH':'0','wsgi.input':io.BytesIO(b'')},start)).decode()
        self.assertEqual(response['status'],'403 Forbidden')
        for phrase in ('/static/style.css','Your sign-in form expired','autocomplete="current-password"','name="csrf"'): self.assertIn(phrase,body)
        token,_=self.user('admin')
        missing=self.request('/unknown-page',token=token)
        self.assertEqual(missing['status'],'404 Not Found')
        self.assertIn('Return home',missing['body'])
        method=self.request('/','DELETE')
        self.assertEqual(method['status'],'405 Method Not Allowed')
        self.assertIn('/static/style.css',method['body'])

    def test_profile_picture_and_private_inbox(self):
        from voiceservices import account,branding
        token,user=self.user('alice');other_token,other=self.user('admin')
        image=b'\xff\xd8\xffexample\xff\xd9'
        account.upload_photo(self.app,user,image)
        self.assertEqual(account.photo(self.app,user)[0],image)
        self.assertIsNone(account.photo(self.app,other))
        account.notify(self.app,user['id'],'Private notice','Only Alice can read this.')
        messages=account.inbox(self.app,user)
        key=next(m['id'] for m in messages if m['title']=='Private notice')
        account.change(self.app,other,{'action':'delete-notification','notification':str(key)},other_token)
        self.assertTrue(any(m['id']==key for m in account.inbox(self.app,user)))
        account.change(self.app,user,{'action':'read-notification','notification':str(key)},token)
        self.assertTrue(next(m['is_read'] for m in account.inbox(self.app,user) if m['id']==key))
        body=self.request('/account/inbox',token=token)['body']
        self.assertIn('Notification inbox',body);self.assertIn('/account/photo/upload',self.request('/account',token=token)['body'])
        self.assertNotIn('Private notice',self.request('/account',token=other_token)['body'])
        branding.upload_logo(self.app,image,'header-fill')
        self.assertEqual(branding.logo(self.app,'header-fill')[0],image)
        self.assertIn('Upload secondary masthead',self.request('/admin/branding',token=other_token)['body'])

    def test_account_sections_are_separate_pages(self):
        token,_=self.user('alice')
        profile=self.request('/account',token=token)['body']
        self.assertNotIn('Password and security',profile)
        self.assertNotIn('Notification inbox',profile)
        self.assertIn('Password and security',self.request('/account/security',token=token)['body'])
        self.assertIn('Notification inbox',self.request('/account/inbox',token=token)['body'])

    def test_logout_confirmation_and_redirect_page(self):
        token,user=self.user('alice')
        response=self.request('/logout','POST',{'csrf':user['csrf']},token)
        self.assertIn('Are you sure',response['body'])
        self.assertIsNotNone(self.app.store.session(token))
        response=self.request('/logout','POST',{'csrf':user['csrf'],'confirm':'yes'},token)
        self.assertEqual(response['headers']['Location'],'/logged-out')
        self.assertIsNone(self.app.store.session(token))
        response=self.request('/logged-out')
        self.assertIn('You have been logged out',response['body'])
        self.assertEqual(response['headers']['Refresh'],'5; url=/login')

    def test_custom_auth_box_text_and_persistent_login(self):
        from voiceservices import branding
        token,user=self.user('admin')
        branding.change(self.app,'branding',{'title':'CasualNetworks','subtitle':'ServiceReady INSAP','login_title':'Hello there','login_subtitle':'My network','create_title':'Join us','create_subtitle':'Get started'})
        body=self.request('/login')['body']
        self.assertIn('Hello there',body);self.assertIn('My network',body)
        self.assertIn('Join us',self.request('/create-account')['body'])
        response=self.request('/login','POST',{'username':'alice','password':'a-long-password','remember':'yes'})
        self.assertIn('Max-Age=2592000',response['headers']['Set-Cookie'])
