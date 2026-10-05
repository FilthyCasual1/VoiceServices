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
        for value in ('Your profile','Password and security','Active sessions','Linked services','alice@example.local','America/Chicago'): self.assertIn(value,response['body'])
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
