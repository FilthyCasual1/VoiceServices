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
        for item in ('Accounts','Host memory','Active portal sessions','Downloads','Voice Services','Boot disk','Installed addons'): self.assertIn(item,body)
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
        self.assertIn('src="/branding/logo?v=',self.request()['body'])
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
        self.assertIn('CasualNetworks Service Ready',body)
        from voiceservices.version import __version__,__codename__
        self.assertIn(__version__+' '+__codename__,body)
        token,user=self.user('admin')
        legend=self.request('/admin/home',token=token)['body']
        for phrase in ('Page links legend','/create-account','/account','/my-phone'): self.assertIn(phrase,legend)
        self.request('/admin/branding','POST',{'csrf':user['csrf'],'title':'Example Network','subtitle':'My services'},token)
        body=self.request()['body'];self.assertIn('<strong>Example Network</strong>',body)
        self.assertIn('Example Network | Powered By CasualNetworks ServiceReady',body)

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

    def test_custom_logout_text_and_look_and_feel(self):
        from voiceservices import branding
        branding.change(self.app,'branding',{'title':'CasualNetworks','subtitle':'ServiceReady INSAP','logout_title':'Leave <now>?','logout_message':'Please confirm departure','logged_out_title':'Goodbye Alice','logged_out_message':'Come back soon'})
        token,user=self.user('alice')
        body=self.request('/logout','POST',{'csrf':user['csrf']},token)['body']
        self.assertIn('Leave &lt;now&gt;?',body);self.assertIn('Please confirm departure',body)
        body=self.request('/logged-out')['body'];self.assertIn('Goodbye Alice',body);self.assertIn('Come back soon',body)
        token,_=self.user('admin');body=self.request('/admin/branding',token=token)['body']
        self.assertIn('Appearance',body);self.assertIn('name="logout_title"',body)

    def test_login_disclaimer_toggle_and_escaping(self):
        from voiceservices import branding
        data={'title':'CasualNetworks','subtitle':'ServiceReady INSAP','login_disclaimer':'Internal <network> only.','login_disclaimer_enabled':'yes'}
        branding.change(self.app,'branding',data)
        self.assertIn('Internal &lt;network&gt; only.',self.request('/login')['body'])
        data['login_disclaimer_enabled']='no';branding.change(self.app,'branding',data)
        self.assertNotIn('Internal &lt;network&gt; only.',self.request('/login')['body'])

    def test_notification_priority_and_private_unread_indicator(self):
        from voiceservices import notifications
        token,alice=self.user('alice');_,admin=self.user('admin');_,bob=self.user('bob')
        notifications.change(self.app,admin,{'recipient':str(alice['id']),'title':'Action needed','body':'Check your service','priority':'urgent'})
        body=self.request(token=token)['body']
        self.assertIn('1 unread notifications; highest priority urgent',body)
        self.assertIn('priority-urgent',self.request('/account/inbox',token=token)['body'])
        self.assertNotIn('notification-indicator',self.request(token=self.app.store.login('bob','a-long-password'))['body'])
        self.request('/account/inbox','POST',{'csrf':alice['csrf'],'action':'read-all-notifications'},token)
        self.assertNotIn('notification-indicator',self.request(token=token)['body'])
        with self.assertRaises(ValueError): notifications.change(self.app,admin,{'recipient':str(bob['id']),'title':'Bad','body':'Bad','priority':'invalid'})

    def test_combined_users_and_recovery_routes(self):
        from voiceservices import recovery
        token,admin=self.user('admin')
        page=self.request('/admin/users',token=token)['body']
        self.assertIn('Users and Accounts',page);self.assertIn('value="authorize-recovery"',page)
        self.assertNotIn('href="/admin/recovery"',page)
        with patch.object(recovery,'issue',return_value='Recovery authorized') as issue:
            result=self.request('/admin/users','POST',{'csrf':admin['csrf'],'action':'authorize-recovery','username':'alice'},token)
            self.assertIn('Recovery authorized',result['body']);issue.assert_called_once()
        self.assertEqual(self.request('/admin/recovery',token=token)['headers']['Location'],'/admin/users#recovery')

    def test_global_timezone_and_date_time_formats(self):
        from voiceservices import branding,regional,update_schedule
        from datetime import datetime,timezone
        values={'title':'CasualNetworks','subtitle':'ServiceReady INSAP','global_timezone':'America/Chicago','date_format':'day-first','time_format':'12-hour'}
        branding.change(self.app,'branding',values)
        stamp=int(datetime(2026,1,2,15,4,tzinfo=timezone.utc).timestamp())
        self.assertEqual(regional.format_timestamp(self.app,stamp),'02/01/2026 09:04 AM CST')
        self.assertEqual(update_schedule.settings(self.app)['os']['effective_timezone'],'America/Chicago')
        token,user=self.user('admin');page=self.request('/admin/branding',token=token)['body']
        self.assertIn('name="global_timezone"',page);self.assertIn('name="date_format"',page)
        with self.assertRaises(ValueError): branding.change(self.app,'branding',dict(values,date_format='unsafe'))
        with self.assertRaises(ValueError): branding.change(self.app,'branding',dict(values,global_timezone='Invalid/Zone'))

    def test_overview_live_endpoint_and_oem_identity(self):
        import json
        from voiceservices import overview
        token,_=self.user('admin')
        response=self.request('/admin/overview-stats',token=token)
        self.assertEqual(response['status'],'200 OK')
        body=json.loads(response['body'])['html']
        self.assertIn('Current date and time',body)
        self.assertNotIn('<header',body)
        self.assertEqual(self.request('/admin/overview-stats',token=self.user('alice')[0])['status'],'403 Forbidden')
        with patch.object(overview.Path,'read_text',side_effect=lambda path=None: ''):
            self.assertIn('OEM identity',str(overview.oem_info()))
        with patch.object(overview.Path,'read_text',return_value='VMware, Inc.'):
            rows=dict(overview.oem_info())
            self.assertEqual(rows['Manufacturer'],'VMware, Inc.')
            self.assertEqual(rows['Model'],'VMware, Inc.')

    def test_static_assets_revalidate_without_resending_image(self):
        response={}
        def start(status,headers): response.update(status=status,headers=dict(headers))
        env={'PATH_INFO':'/branding/masthead','REQUEST_METHOD':'GET'}
        image=b''.join(self.app(env,start))
        self.assertTrue(image)
        etag=response['headers']['ETag']
        env['HTTP_IF_NONE_MATCH']=etag
        self.assertEqual(b''.join(self.app(env,start)),b'')
        self.assertEqual(response['status'],'304 Not Modified')
        body=self.request()['body']
        self.assertIn('/static/portal.js?v=',body)

    def test_separate_home_audiences(self):
        token,admin=self.user('admin')
        for audience,title in [('guest','Guest only'),('signed-in','Member only')]:
            self.request('/admin/home','POST',{'csrf':admin['csrf'],'title':title,'body':'Test','audience':audience,'enabled':'yes'},token)
        guest=self.request()['body'];member=self.request(token=token)['body']
        self.assertIn('Guest only',guest);self.assertNotIn('Member only',guest)
        self.assertIn('Member only',member);self.assertNotIn('Guest only',member)
        self.assertNotIn('<h2>1. Get an account',member)

    def test_timezone_dropdowns_and_friendly_defaults(self):
        token,_=self.user('admin')
        for path,name in [('/admin/branding','global_timezone'),('/account','timezone'),('/admin/schedules','os_timezone')]:
            page=self.request(path,token=token)['body']
            self.assertRegex(page,r'<select[^>]*name="'+name+r'"')
            self.assertIn('value="America/Chicago"',page)
        self.assertNotIn('before going live',self.request('/login')['body'])
        self.assertIn('Access your account and network services.',self.request('/login')['body'])
        from voiceservices import branding
        with self.app.store.connect() as db: db.execute("UPDATE home_blocks SET body='Custom welcome' WHERE title='1. Get an account'")
        branding.initialize(self.app)
        self.assertIn('Custom welcome',self.request()['body'])

    def test_domain_and_hostname_in_account_header(self):
        from voiceservices.web import App
        with patch('voiceservices.web.socket.gethostname',return_value='portal'),patch('voiceservices.web.socket.getfqdn',return_value='portal.example.org'):
            app=App({'database':self.tmp.name+'/domain.sqlite','secure_cookies':False})
            self.assertEqual(app.host_label,'example.org/portal')
            self.assertIn('example.org/portal',app.page('Home','',None))
        with patch('voiceservices.web.socket.gethostname',return_value='new'),patch('voiceservices.web.socket.getfqdn',return_value='new.example.net'):
            self.assertEqual(app.host_label,'example.net/new')

    def test_overview_has_identity_but_updates_only_on_updates_page(self):
        token,user=self.user('admin')
        body=self.request('/admin',token=token)['body']
        self.assertIn('Powered by',body);self.assertIn('/host/distro-logo',body);self.assertIn('Installed INSAP version:',body)
        self.assertNotIn('>Update OS</button>',body);self.assertNotIn('>Grab INSAP update</button>',body);self.assertNotIn('data-update-state',body)
        updates=self.request('/admin/system-updates',token=token)['body']
        self.assertIn('>Update OS</button>',updates);self.assertIn('>Grab INSAP update</button>',updates)
        with patch('voiceservices.maintenance.change') as change:
            response=self.request('/admin','POST',{'csrf':user['csrf'],'update':'insap'},token)
        self.assertEqual(response['status'],'400 Bad Request');change.assert_not_called()
