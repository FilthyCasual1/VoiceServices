import io,json,unittest,zipfile
from unittest.mock import patch
import test_app
from addon_support import install,package

class PackageTests(unittest.TestCase):
    setUp=test_app.PortalTests.setUp
    tearDown=test_app.PortalTests.tearDown
    request=test_app.PortalTests.request
    user=test_app.PortalTests.user
    def test_install_is_file_based_and_uninstall_deletes_code(self):
        module='downloads';directory=self.app.modules.root/module
        self.assertTrue((directory/'module.py').is_file())
        self.app.modules.change(module,False)
        self.assertFalse(directory.exists())
        self.assertEqual(self.request('/downloads')['status'],'404 Not Found')
        with self.assertRaises(ValueError): self.app.modules.change(module,True)
        install(self.app,module)
        self.assertTrue((directory/'module.py').is_file())
        self.assertEqual(self.request('/downloads')['status'],'200 OK')
    def test_rejects_tampering_and_archive_traversal(self):
        self.app.modules.change('downloads',False)
        for name in ('module.py','../outside.py'):
            out=io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(package('downloads'))) as original,zipfile.ZipFile(out,'w') as altered:
                altered.writestr('manifest.json',original.read('manifest.json'))
                altered.writestr(name,b'raise RuntimeError("untrusted code")')
            with self.assertRaises(ValueError): self.app.modules.install(out.getvalue())
        self.assertFalse(self.app.modules.installed('downloads'))
    def test_package_upload_auth_csrf_and_install(self):
        self.app.modules.change('downloads',False)
        token,user=self.user('admin');payload=package('downloads')
        def upload(csrf,session):
            body=b'--Pkg\r\nContent-Disposition: form-data; name="csrf"\r\n\r\n'+csrf.encode()+b'\r\n--Pkg\r\nContent-Disposition: form-data; name="file"; filename="downloads.sraddon"\r\nContent-Type: application/octet-stream\r\n\r\n'+payload+b'\r\n--Pkg--\r\n'
            env={'PATH_INFO':'/admin/addons/upload','REQUEST_METHOD':'POST','CONTENT_TYPE':'multipart/form-data; boundary=Pkg','CONTENT_LENGTH':str(len(body)),'wsgi.input':io.BytesIO(body),'HTTP_COOKIE':'vs_session='+session}
            response={}
            def start(status,headers): response.update(status=status,headers=dict(headers))
            b''.join(self.app(env,start));return response
        self.assertEqual(upload('wrong',token)['status'],'403 Forbidden')
        other,_=self.user('alice');self.assertEqual(upload('wrong',other)['status'],'403 Forbidden')
        self.assertEqual(upload(user['csrf'],token)['status'],'303 See Other')
        self.assertTrue(self.app.modules.installed('downloads'))
    def test_esxi_credentials_and_power_confirmation(self):
        install(self.app,'esxi');token,user=self.user('admin')
        addon=self.app.modules.load('esxi')
        saved=self.request('/admin/esxi','POST',{'csrf':user['csrf'],'host':'https://esxi.local','username':'operator'},token)
        self.assertEqual(saved['status'],'200 OK')
        with patch.object(addon,'Client') as client:
            client.return_value.inventory.return_value=[{'id':'vm-1','type':'VirtualMachine','values':{'name':'Test VM','runtime.powerState':'poweredOff'}}]
            result=self.request('/esxi','POST',{'csrf':user['csrf'],'password':'secret','action':'inventory'},token)
            self.assertIn('Test VM',result['body']);self.assertNotIn('secret',result['body'])
            self.request('/esxi','POST',{'csrf':user['csrf'],'password':'secret','action':'power-off','vm':'vm-1'},token)
            client.return_value.power.assert_not_called()
            self.request('/esxi','POST',{'csrf':user['csrf'],'password':'secret','action':'power-on','vm':'vm-1','confirm':'yes'},token)
            client.return_value.power.assert_called_once_with('vm-1','power-on')
        self.assertEqual(self.request('/esxi',token=self.user('alice')[0])['status'],'403 Forbidden')
        self.app.modules.change('esxi',False)
        self.assertEqual(self.request('/esxi',token=token)['status'],'404 Not Found')
    def test_voice_mapping_refresh_and_cucm_creation(self):
        token,admin=self.user('admin');voice=self.app.modules.load('voice')
        response=self.request('/admin/voice','POST',{'csrf':admin['csrf'],'username':'alice','userid':'alice-phone','action':'link'},token)
        self.assertEqual(response['status'],'200 OK')
        other=self.request('/admin/voice','POST',{'csrf':admin['csrf'],'username':'bob','userid':'alice-phone','action':'link'},token)
        self.assertEqual(other['status'],'400 Bad Request')
        alice,person=self.user('alice')
        with patch.object(voice,'axl_user',return_value={'userid':'alice-phone','firstName':'Alice','lastName':'Example','extension':'1234'}):
            response=self.request('/account','POST',{'csrf':person['csrf'],'action':'voice-refresh'},alice)
            self.assertIn('1234',response['body'])
        self.assertNotIn('1234',self.request('/account',token=self.user('bob')[0])['body'])
        from xml.etree import ElementTree as ET
        success=ET.fromstring('<Envelope><addUserResponse><return>{user-id}</return></addUserResponse></Envelope>')
        data={'csrf':admin['csrf'],'username':'bob','userid':'bob-phone','action':'create-cucm','first_name':'Bob & Sons','last_name':'Example','cucm_password':'cucm-test-password','cucm_pin':'123456'}
        with patch.object(voice,'axl_request',return_value=success) as request:
            self.assertEqual(self.request('/admin/voice','POST',data,token)['status'],'400 Bad Request');request.assert_not_called()
            data['confirm']='yes';response=self.request('/admin/voice','POST',data,token)
            self.assertEqual(response['status'],'200 OK');request.assert_called_once()
            method,payload=request.call_args.args[1:];self.assertEqual(method,'addUser');self.assertIn('Bob &amp; Sons',payload)
            self.assertNotIn('cucm-test-password',response['body']);self.assertNotIn('123456',response['body'])
            with self.app.store.connect() as db:
                row=db.execute("SELECT userid,profile FROM voice_user_links JOIN users ON users.id=voice_user_links.user_id WHERE username='bob'").fetchone()
                self.assertEqual(row['userid'],'bob-phone');self.assertNotIn('cucm-test-password',row['profile'])
    def test_axl_envelope_and_credential_handling(self):
        from xml.etree import ElementTree as ET
        voice=self.app.modules.load('voice');self.app.config['voice_axl_url']='https://call.local:8443/axl/'
        response=io.BytesIO(b'<Envelope><getUserResponse><return><user><userid>alice</userid><firstName>Alice</firstName><primaryExtension><pattern>1234</pattern></primaryExtension></user></return></getUserResponse></Envelope>')
        with patch.dict(voice.os.environ,{'SERVICEREADY_AXL_USERNAME':'axl-service','SERVICEREADY_AXL_PASSWORD':'axl-secret'}),patch.object(voice,'urlopen',return_value=response) as send:
            data=voice.axl_user(self.app,'alice');self.assertEqual(data['extension'],'1234')
            request=send.call_args.args[0];self.assertIn('getUser',request.headers['Soapaction'])
            ET.fromstring(request.data);self.assertNotIn(b'axl-secret',request.data)
