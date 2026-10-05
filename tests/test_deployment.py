import io
import hashlib
import unittest
import test_app

class DeploymentTests(unittest.TestCase):
    setUp=test_app.PortalTests.setUp
    tearDown=test_app.PortalTests.tearDown
    request=test_app.PortalTests.request
    user=test_app.PortalTests.user

    def test_download_catalog_lifecycle(self):
        self.app.downloads.add_link(dict(title='Internal agent',version='1.0',platform='Linux',url='https://tools.local/agent'))
        self.assertIn('Internal agent',self.request('/downloads')['body'])
        with self.assertRaises(ValueError): self.app.downloads.add_link(dict(title='bad',url='javascript:alert(1)'))
        self.app.modules.change('downloads',False)
        self.assertEqual(self.request('/downloads')['status'],'404 Not Found')
        self.assertNotIn('href="/downloads"',self.request()['body'])
        self.app.modules.change('downloads',True)
        self.assertIn('Internal agent',self.request('/downloads')['body'])

    def test_binary_ranges_and_head(self):
        repo=self.app.downloads
        repo.root.mkdir(parents=True,exist_ok=True)
        payload=b'0123456789';(repo.root/'agent.bin').write_bytes(payload)
        with self.app.store.connect() as db:
            db.execute('INSERT INTO downloads_files(name,size,sha256) VALUES(?,?,?)',('agent.bin',10,hashlib.sha256(payload).hexdigest()))
        def fetch(method='GET',byte_range=''):
            response={};env={'REQUEST_METHOD':method,'HTTP_RANGE':byte_range}
            def start(status,headers): response.update(status=status,headers=dict(headers))
            response['body']=b''.join(repo.serve(env,start,'agent.bin'));return response
        self.assertEqual(fetch()['body'],payload)
        self.assertEqual(fetch('HEAD')['body'],b'')
        self.assertEqual(fetch(byte_range='bytes=3-5')['body'],b'345')
        self.assertEqual(fetch(byte_range='bytes=-2')['body'],b'89')
        self.assertEqual(fetch(byte_range='bytes=99-')['status'],'416 Range Not Satisfiable')

    def test_pxe_profiles_and_removal(self):
        self.app.modules.change('pxe',True)
        self.app.pxe.change(dict(action='profile',title='Rescue ISO',kind='iso',iso='http://boot.local/rescue.iso'))
        self.app.pxe.change(dict(action='profile',title='Restore',kind='restore',kernel='http://boot.local/vmlinuz',initrd='http://boot.local/initrd.img',squashfs='http://boot.local/filesystem.squashfs',repository='nfs://storage.local/images'))
        script=self.request('/pxe/boot.ipxe')['body']
        self.assertTrue(script.startswith('#!ipxe'))
        self.assertIn('sanboot --no-describe http://boot.local/rescue.iso',script)
        self.assertIn('ocs_live_batch=no',script)
        self.assertIn('restoredisk ask_user ask_user',script)
        with self.assertRaises(ValueError): self.app.pxe.change(dict(action='profile',title='bad',kind='iso',iso='http://boot.local/a;reboot'))
        with self.assertRaises(ValueError): self.app.pxe.change(dict(action='network',enabled='yes',subnet='192.168.10.0/24',address='192.168.10.2'))
        token,user=self.user('admin')
        for path in ('/admin/downloads','/admin/pxe'): self.assertEqual(self.request(path,token=token)['status'],'200 OK')
        self.app.modules.change('pxe',False)
        self.assertEqual(self.request('/pxe/boot.ipxe')['status'],'404 Not Found')

    def test_bare_bootstrap_persists_installs_and_removals(self):
        from voiceservices.web import App
        config={'database':self.tmp.name+'/bare.sqlite','initial_modules':[],'secure_cookies':False}
        app=App(config)
        for name in ('downloads','voice','server-management','pxe'): self.assertFalse(app.modules.installed(name))
        self.assertIsNone(app.updates.settings())
        app.modules.change('downloads',True)
        app=App(config)
        self.assertTrue(app.modules.installed('downloads'))
        app.modules.change('downloads',False)
        app=App(config)
        self.assertFalse(app.modules.installed('downloads'))
        app.store.create_user('operator','long-enough-password','admin')
        token=app.store.login('operator','long-enough-password')
        self.assertEqual(app.store.session(token)['role'],'admin')
