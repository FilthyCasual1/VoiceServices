from pathlib import Path
import io
import json
import tempfile
import unittest
from urllib.parse import urlencode
from xml.etree import ElementTree as ET
from voiceservices.core import calculate
from voiceservices.web import App


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App({'database':self.tmp.name+'/db.sqlite','secure_cookies':False})
        from addon_support import install
        for name in ('voice','downloads','server-management'): install(self.app,name)
        self.app.store.create_user('admin','a-long-password','admin')
        self.app.store.create_user('alice','a-long-password')
        self.app.store.create_user('bob','a-long-password')

    def tearDown(self): self.tmp.cleanup()

    def request(self,path='/',method='GET',data=None,token='',query=''):
        if path == '/login' and method == 'POST':
            from http.cookies import SimpleCookie
            cookies = SimpleCookie()
            cookies.load(self.request('/login')['headers']['Set-Cookie'])
            nonce = cookies['vs_login'].value
            data = dict(data or {}, csrf=nonce)
            token += '; vs_login='+nonce
        body = urlencode(data or {}).encode()
        response = {}
        env = {'PATH_INFO':path,'REQUEST_METHOD':method,'QUERY_STRING':query,
               'CONTENT_LENGTH':str(len(body)),'wsgi.input':io.BytesIO(body),
               'HTTP_COOKIE':'vs_session='+token,'REMOTE_ADDR':'127.0.0.1'}
        def start(status,headers): response.update(status=status,headers=dict(headers))
        response['body'] = b''.join(self.app(env,start)).decode()
        return response

    def user(self,name):
        token = self.app.store.login(name,'a-long-password')
        return token,self.app.store.session(token)

    def test_login_logout_and_csrf(self):
        self.assertEqual(self.request()['status'],'200 OK')
        token,user = self.user('alice')
        self.assertIn('alice',self.request(token=token)['body'])
        self.assertEqual(self.request('/logout','POST',token=token)['status'],'403 Forbidden')
        self.request('/logout','POST',{'csrf':user['csrf'],'confirm':'yes'},token)
        self.assertIsNone(self.app.store.session(token))

    def test_public_portal_requires_login_for_edits(self):
        for route in ['/', '/downloads']:
            r = self.request(route)
            self.assertEqual(r['status'],'200 OK')
            self.assertNotIn('<aside>',r['body'])
            self.assertNotIn('href="/admin"',r['body'])
            self.assertNotIn('Sign in to edit',r['body'])
            self.assertIn('href="/login">Sign in</a>',r['body'])
            self.assertNotIn('Current user:',r['body'])
            for text in ('Cisco','CUCM','12.5','Unity Connection'): self.assertNotIn(text,r['body'])
        for route in ['/admin','/applications','/directory','/my-phone','/recordings','/network']:
            self.assertEqual(self.request(route)['headers']['Location'],'/login')
        self.assertEqual(self.request('/directory','POST',{'name':'Anonymous','number':'1'})['status'],'303 See Other')
        self.assertIn('Welcome to CasualNetworks',self.request()['body'])
        self.assertIn('Get an account',self.request()['body'])
        self.assertNotIn('System status',self.request()['body'])

    def test_login_cookie_and_bad_password(self):
        r=self.request('/login','POST',{'username':'alice','password':'a-long-password'})
        self.assertIn('HttpOnly',r['headers']['Set-Cookie'])
        self.assertIn('SameSite=Lax',r['headers']['Set-Cookie'])
        self.assertIsNone(self.app.store.login('alice','wrong'))

    def test_role_and_contact_isolation(self):
        token,alice=self.user('alice')
        _,bob=self.user('bob')
        _,admin=self.user('admin')
        self.app.store.add_contact(alice,'Private','+15551234567')
        self.app.store.add_contact(admin,'Shared','201',True)
        self.assertEqual(len(self.app.store.contacts(bob['id'])),1)
        self.assertEqual(self.request('/admin',token=token)['status'],'403 Forbidden')
        with self.assertRaises(PermissionError): self.app.store.add_contact(alice,'Bad','123',True)
        self.assertEqual(self.request('/directory','POST',{'name':'CSRF','number':'1'},token)['status'],'403 Forbidden')

    def test_phone_roaming_revokes_previous_token_and_logout(self):
        _,alice=self.user('alice')
        self.app.store.preferences(alice['id'],{'weather_location':'Chicago'})
        old=self.app.store.bind_phone(alice,'SEP001122AABBCC')
        new=self.app.store.bind_phone(alice,'SEP001122AABBDD')
        self.assertIsNone(self.app.store.phone_user(old))
        self.assertEqual(json.loads(self.app.store.phone_user(new)['preferences'])['weather_location'],'Chicago')
        self.app.store.unbind_phone(alice['id'])
        self.assertIsNone(self.app.store.phone_user(new))

    def test_phone_xml_and_escaping(self):
        _,alice=self.user('alice')
        self.app.store.add_contact(alice,'A & <B>','201')
        token=self.app.store.bind_phone(alice,'SEP001122AABBCC')
        for route,root in [('services','CiscoIPPhoneMenu'),('directory','CiscoIPPhoneDirectory'),('calculator','CiscoIPPhoneInput')]:
            r=self.request('/phone/'+route,query=urlencode({'token':token}))
            self.assertEqual(r['status'],'200 OK')
            parsed=ET.fromstring(r['body'])
            self.assertEqual(parsed.tag,root)
            if route=='directory': self.assertEqual(parsed.find('DirectoryEntry/Name').text,'A & <B>')
        self.assertEqual(self.request('/phone/services')['status'],'403 Forbidden')

    def test_calculator_no_eval_and_errors(self):
        self.assertEqual(calculate('0.1','add','0.2'),'0.3')
        self.assertEqual(calculate('12','divide','4'),'3')
        for args in [('1','divide','0'),('NaN','add','2'),('__import__("os")','add','2'),('1','pow','2'),('1e-999999','add','2')]:
            with self.assertRaises(ValueError): calculate(*args)

    def test_html_escaping_and_link_validation(self):
        token,alice=self.user('alice')
        self.app.store.add_contact(alice,'<script>alert(1)</script>','201')
        page=self.request('/directory',token=token)['body']
        self.assertNotIn('<script>',page)
        self.assertIn('&lt;script&gt;',page)
        self.assertFalse(self.app.valid_link('javascript:alert(1)'))
        self.assertFalse(self.app.valid_link('https://admin:secret@example.com'))
        self.assertTrue(self.app.valid_link('https://cucm.example.com/ccmadmin'))

    def test_routes_and_no_simulated_health(self):
        token,user=self.user('admin')
        for route in ['/','/admin','/downloads','/applications','/my-phone','/recordings','/network']:
            r=self.request(route,token=token)
            self.assertEqual(r['status'],'200 OK',route)
        self.assertIn('System overview',self.request('/admin',token=token)['body'])
        for route in ['/apps/calculator','/apps/weather','/apps/rss','/apps/flights']:
            self.assertEqual(self.request(route,token=token)['status'],'404 Not Found')
        self.assertNotIn('href="/apps/',self.request('/applications',token=token)['body'])
        self.assertEqual(self.request('/unknown',token=token)['status'],'404 Not Found')

    def test_native_self_provisioning_details_are_private(self):
        self.app.config['self_provisioning'] = {'ivr_number': '5000', 'users': {'alice': {'user_id': 'alice-cucm', 'self_service_id': '201', 'extension': '201'}}}
        public = self.request('/my-phone')
        self.assertEqual(public['headers']['Location'], '/login')
        self.assertNotIn('alice-cucm', public['body'])
        token, _ = self.user('alice')
        self.assertIn('alice-cucm', self.request('/my-phone', token=token)['body'])
        other, _ = self.user('bob')
        self.assertNotIn('alice-cucm', self.request('/my-phone', token=other)['body'])
        self.assertNotIn('Submit registration', public['body'])

    def test_my_phone_consolidation(self):
        token, _ = self.user('alice')
        page = self.request('/my-phone',token=token)['body']
        for section in ['Phone setup','Line keys and customization','Phone application settings']:
            self.assertIn(section,page)
        self.assertNotIn('>Set Up Phone</a>',page)
        self.assertNotIn('>Phone Customization</a>',page)
        self.assertNotIn('>Phone Settings</a>',page)
        for route,anchor in [('/register-phone','setup'),('/self-care','customization'),('/preferences','settings')]:
            r = self.request(route)
            self.assertEqual(r['headers']['Location'],'/my-phone#'+anchor)
        token,user = self.user('alice')
        result = self.request('/my-phone','POST',{'csrf':user['csrf'],'action':'preferences','weather_location':'Chicago','widget':'network'},token)
        self.assertEqual(result['headers']['Location'],'/my-phone#settings')
        self.assertEqual(json.loads(self.app.store.session(token)['preferences'])['weather_location'],'Chicago')

    def test_expiry_and_rebinding_device(self):
        _,alice=self.user('alice')
        _,bob=self.user('bob')
        old=self.app.store.bind_phone(alice,'SEP001122AABBCC')
        new=self.app.store.bind_phone(bob,'SEP001122AABBCC')
        self.assertIsNone(self.app.store.phone_user(old))
        with self.app.store.connect() as db: db.execute('UPDATE phones SET expires=0')
        self.assertIsNone(self.app.store.phone_user(new))

    def test_plugin_management_requires_admin_and_csrf(self):
        package = Path('plugins/site-information/plugin.json').read_text()
        token,user = self.user('alice')
        self.assertEqual(self.request('/applications','POST',{'csrf':user['csrf'],'action':'install','manifest':package},token)['status'],'403 Forbidden')
        token,user = self.user('admin')
        self.assertEqual(self.request('/applications','POST',{'action':'install','manifest':package},token)['status'],'403 Forbidden')
        self.assertEqual(self.request('/applications','POST',{'csrf':user['csrf'],'action':'install','manifest':package},token)['status'],'303 See Other')
        self.assertIn('Site Information',self.request('/applications',token=token)['body'])
        self.assertNotIn('name="manifest"',self.request('/applications')['body'])

    def test_registration_is_user_only_and_signs_in(self):
        import re
        page = self.request('/create-account')
        nonce = re.search('name="csrf" value="([^"]+)"',page['body'])[1]
        data = {'csrf':nonce,'username':'new-user','password':'a-new-long-password','confirm_password':'a-new-long-password','role':'admin'}
        self.assertEqual(self.request('/create-account','POST',data)['status'],'403 Forbidden')
        result = self.request('/create-account','POST',data,'unused; vs_signup='+nonce)
        self.assertEqual(result['headers']['Location'],'/')
        token = self.app.store.login('new-user','a-new-long-password')
        user = self.app.store.session(token)
        self.assertEqual(user['role'],'user')
        self.assertIn('Hello, new-user.',self.request(token=token)['body'])
        self.assertIn('Log out',self.request(token=token)['body'])
        duplicate = self.request('/create-account','POST',data,'unused; vs_signup='+nonce)
        self.assertIn('already in use',duplicate['body'])


    def test_login_form_survives_another_tab_and_expired_form_recovers(self):
        from http.cookies import SimpleCookie
        first=self.request('/login');cookies=SimpleCookie();cookies.load(first['headers']['Set-Cookie'])
        nonce=cookies['vs_login'].value
        second=self.request('/login',token='; vs_login='+nonce)
        self.assertIn('value="'+nonce+'"',second['body'])
        def post(csrf,cookie):
            body=urlencode({'username':'alice','password':'a-long-password','csrf':csrf}).encode();response={}
            env={'PATH_INFO':'/login','REQUEST_METHOD':'POST','CONTENT_LENGTH':str(len(body)),'wsgi.input':io.BytesIO(body),'HTTP_COOKIE':cookie,'REMOTE_ADDR':'127.0.0.1'}
            def start(status,headers): response.update(status=status,headers=dict(headers))
            response['body']=b''.join(self.app(env,start)).decode();return response
        self.assertEqual(post(nonce,'vs_login='+nonce)['status'],'303 See Other')
        expired=post(nonce,'')
        self.assertEqual(expired['status'],'403 Forbidden')
        self.assertIn('autocomplete="current-password"',expired['body'])
        fresh=SimpleCookie();fresh.load(expired['headers']['Set-Cookie']);fresh_nonce=fresh['vs_login'].value
        self.assertEqual(post(fresh_nonce,'vs_login='+fresh_nonce)['status'],'303 See Other')

if __name__=='__main__': unittest.main()
