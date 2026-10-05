import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from voiceservices.core import Store
from voiceservices.updates import Updates
from voiceservices.web import App
import test_app

class AdministrationTests(unittest.TestCase):
    setUp=test_app.PortalTests.setUp
    tearDown=test_app.PortalTests.tearDown
    request=test_app.PortalTests.request
    user=test_app.PortalTests.user
    def test_password_change_revokes_sessions_and_bindings(self):
        token,user=self.user('alice')
        binding=self.app.store.bind_phone(user,'SEP001122AABBCC')
        result=self.request('/account','POST',{'csrf':user['csrf'],'current_password':'wrong','new_password':'a-new-long-password','confirm_password':'a-new-long-password'},token)
        self.assertEqual(result['status'],'400 Bad Request')
        result=self.request('/account','POST',{'csrf':user['csrf'],'current_password':'a-long-password','new_password':'a-new-long-password','confirm_password':'a-new-long-password'},token)
        self.assertEqual(result['headers']['Location'],'/login')
        self.assertIsNone(self.app.store.session(token));self.assertIsNone(self.app.store.phone_user(binding))
        self.assertIsNone(self.app.store.login('alice','a-long-password'))
        self.assertTrue(self.app.store.login('alice','a-new-long-password'))
    def test_admin_settings_persist_and_invalid_url_is_rejected(self):
        token,user=self.user('admin')
        result=self.request('/admin/settings','POST',{'csrf':user['csrf'],'cucm_admin':'https://call.example/admin','tftp_host':'10.0.0.2'},token)
        self.assertEqual(result['status'],'200 OK')
        new=App({'database':self.app.store.path,'secure_cookies':False})
        self.app=new
        self.assertIn('call.example',self.request('/admin/settings',token=token)['body'])
        self.assertEqual(self.request('/admin/settings','POST',{'csrf':user['csrf'],'cucm_admin':'javascript:alert(1)'},token)['status'],'400 Bad Request')
    def test_addon_install_configure_upload_remove(self):
        token,user=self.user('admin')
        self.request('/admin/addons','POST',{'csrf':user['csrf'],'action':'install'},token)
        self.request('/admin/updates','POST',{'csrf':user['csrf'],'username':'updates','ftp_password':'an-ftp-long-password','port':'2121','passive_start':'30000','passive_end':'30009','enabled':'yes'},token)
        self.assertTrue(self.app.updates.settings()['enabled'])
        content=b'\x00binary\r\ncontents\xff'
        def upload(name,csrf=user['csrf']):
            boundary=b'WebBoundary'
            body=b'--'+boundary+b'\r\nContent-Disposition: form-data; name="csrf"\r\n\r\n'+csrf.encode()+b'\r\n--'+boundary+b'\r\nContent-Disposition: form-data; name="file"; filename="'+name.encode()+b'"\r\nContent-Type: application/octet-stream\r\n\r\n'+content+b'\r\n--'+boundary+b'--\r\n'
            return self.app.updates.upload({'CONTENT_LENGTH':str(len(body)),'CONTENT_TYPE':'multipart/form-data; boundary=WebBoundary','wsgi.input':io.BytesIO(body)},user)
        self.assertEqual(upload('update.iso'),'update.iso')
        self.assertEqual((self.app.updates.root/'update.iso').read_bytes(),content)
        self.assertEqual(self.app.updates.files()[0]['sha256'],hashlib.sha256(content).hexdigest())
        with self.assertRaises(ValueError): upload('update.iso')
        with self.assertRaises(ValueError): upload('../bad.iso')
        with self.assertRaises(PermissionError): upload('other.iso','wrong')
        self.request('/admin/addons','POST',{'csrf':user['csrf'],'action':'remove'},token)
        self.assertIsNone(self.app.updates.settings())
        self.assertTrue((self.app.updates.root/'update.iso').exists())

    def test_modules_hide_routes_and_restore_saved_voice_data(self):
        token,user=self.user('admin')
        self.app.store.add_contact(user,'Keep me','1234')
        self.request('/admin/addons','POST',{'csrf':user['csrf'],'action':'remove','module':'voice'},token)
        for route in ('/my-phone','/directory','/applications','/phone/services','/recordings'):
            self.assertEqual(self.request(route,token=token)['status'],'404 Not Found')
        home=self.request(token=token)['body']
        self.assertNotIn('href="/my-phone"',home)
        self.assertIn('My Account',home)
        for category in ('Storage','Voice','Email','Domain services'): self.assertIn(category,home)
        self.assertIn('System overview',self.request('/admin',token=token)['body'])
        self.request('/admin/addons','POST',{'csrf':user['csrf'],'action':'remove','module':'server-management'},token)
        self.assertEqual(self.request('/admin/settings',token=token)['status'],'404 Not Found')
        self.assertNotIn('Call Management',self.request('/admin',token=token)['body'])
        self.request('/admin/addons','POST',{'csrf':user['csrf'],'action':'install','module':'voice'},token)
        self.assertIn('Keep me',self.request('/directory',token=token)['body'])
        self.assertTrue(self.app.modules.installed('voice'))
        self.assertFalse(self.app.modules.installed('server-management'))

class AccountBackendTests(unittest.TestCase):
    def test_system_passwords_use_broker_and_do_not_grant_admin(self):
        class Broker:
            passwords={'enrolled':'system-password'}
            def call(self,action,name,password,new_password=None):
                if action=='create': self.passwords[name]=password;return True
                if self.passwords.get(name)!=password: raise ValueError('Invalid credentials')
                if action=='change': self.passwords[name]=new_password
                return True
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'db',Broker())
            token=store.login('enrolled','system-password')
            user=store.session(token)
            self.assertEqual(user['role'],'user')
            self.assertIsNone(store.login('enrolled','bad'))
            store.change_password(user,'system-password','replacement-password')
            self.assertIsNone(store.session(token))
            self.assertTrue(store.login('enrolled','replacement-password'))
