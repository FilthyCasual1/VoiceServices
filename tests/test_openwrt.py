import importlib.util,io,json,os,tempfile,unittest,tarfile,zipfile
from pathlib import Path
from unittest.mock import Mock,patch
from urllib.parse import urlencode
from http.cookies import SimpleCookie
ROOT=Path(__file__).parents[1]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
bootstrap=load('ow_bootstrap','deploy/openwrt/bootstrap.py');provider=load('ow_provider','deploy/openwrt/host-provider.py');image=load('ow_image','tools/build_openwrt_image.py');bundle=load('ow_bundle','tools/build_openwrt_bundle.py');ova=load('ow_ova','tools/build_ova.py')
class FirstBootTests(unittest.TestCase):
 def setUp(self):
  from voiceservices.web import App
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.app=App({'database':str(self.root/'db'),'public_url':'https://192.0.2.4','secure_cookies':True,'first_boot_setup':True,'initial_modules':[]});self.app.store.accounts=Mock()
 def tearDown(self):self.tmp.cleanup()
 def request(self,path,method='GET',data=None,cookie=''):
  encoded=urlencode(data or {}).encode();result={}
  env={'PATH_INFO':path,'REQUEST_METHOD':method,'wsgi.input':io.BytesIO(encoded),'CONTENT_LENGTH':str(len(encoded)),'HTTP_COOKIE':cookie,'REMOTE_ADDR':'192.0.2.5','QUERY_STRING':''}
  def start(status,headers):result.update(status=status,headers=headers)
  result['body']=b''.join(self.app(env,start)).decode();return result
 def test_redirect_wizard_and_one_time_close(self):
  self.assertEqual(dict(self.request('/')['headers'])['Location'],'/setup')
  result=self.request('/setup');self.assertIn('data-firstboot-wizard',result['body']);self.assertIn('Setup code',result['body'])
  nonce=SimpleCookie(dict(result['headers'])['Set-Cookie'])['vs_setup'].value
  result=self.request('/setup','POST',{'csrf':nonce,'username':'owner','password':'unique-password','confirm_password':'unique-password','title':'My Portal','timezone':'UTC','setup_code':'unique-code'},'vs_setup='+nonce)
  self.assertIn('Your portal is ready',result['body']);self.app.store.accounts.call.assert_called_once();self.assertEqual(self.app.store.accounts.call.call_args.args[0],'setup-complete')
  self.app.store.accounts=None;self.app.store.create_user('owner','unique-password','admin')
  self.assertEqual(dict(self.request('/setup')['headers'])['Location'],'/login')
 def test_csrf_and_https_required(self):
  response=self.request('/setup','POST',{'password':'unique-password','confirm_password':'unique-password'})
  self.assertIn('expired',response['body']);self.app.store.accounts.call.assert_not_called()
  self.app.secure=False;self.assertEqual(self.request('/setup')['status'],'503 Service Unavailable')
 def test_root_provider_claim_serialization_and_replay(self):
  config=self.root/'config.json';config.write_text(json.dumps({'database':self.app.store.path,'first_boot_setup':True}));token=self.root/'setup-token';token.write_text('correct-code')
  shadow=self.root/'shadow';shadow.write_text('root:existing-password:0:0:99999:7:::\n')
  request={'action':'setup-complete','username':'owner','password':'correct-code','new_password':json.dumps({'password':'unique-password','title':'Mine','timezone':'UTC'})}
  with patch.object(provider,'CONFIG',config),patch.object(provider,'SETUP_LOCK',self.root/'lock'),patch.object(provider,'SHADOW',shadow),patch('pwd.getpwnam',side_effect=KeyError):
   with patch('subprocess.run') as run:
    set_password=Mock();command=Mock(side_effect=lambda action,user:[action,user]);provider.complete_setup(request,command,set_password)
    set_password.assert_called_once_with('owner','unique-password');self.assertFalse(token.exists())
    with self.assertRaisesRegex(ValueError,'already'):provider.complete_setup(request,command,set_password)
  with self.app.store.connect() as db:self.assertEqual(db.execute("SELECT role,password FROM users WHERE username='owner'").fetchone()['password'],'system')
 def test_bad_code_does_not_touch_os(self):
  config=self.root/'config.json';config.write_text(json.dumps({'database':self.app.store.path,'first_boot_setup':True}));(self.root/'setup-token').write_text('real-code')
  req={'username':'owner','password':'wrong','new_password':json.dumps({'password':'unique-password','title':'Mine','timezone':'UTC'})}
  with patch.object(provider,'CONFIG',config),patch.object(provider,'SETUP_LOCK',self.root/'lock'),patch('subprocess.run') as run:
   with self.assertRaisesRegex(ValueError,'incorrect'):provider.complete_setup(req,Mock(),Mock())
   run.assert_not_called()
class TLSAndMenuTests(unittest.TestCase):
 def test_ca_identity_retained_when_dhcp_changes_ipv4_and_ipv6(self):
  from voiceservices import openwrt_tls
  from subprocess import check_output
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);addresses=Mock();addresses.current.return_value=(['192.0.2.4'],'192.0.2.4')
   config=bootstrap.configuration();openwrt_tls.refresh(config,addresses,root=root,reload=False)
   ca=root/'etc/serviceready/tls/ca.key';original=ca.read_bytes()
   addresses.current.return_value=(['192.0.2.5','2001:db8::5'],'192.0.2.5')
   url=openwrt_tls.refresh(config,addresses,root=root,reload=False)
   self.assertEqual(url,'https://192.0.2.5');self.assertEqual(ca.read_bytes(),original)
   cert=root/'etc/serviceready/tls/server.crt';text=check_output(['openssl','x509','-in',str(cert),'-noout','-text'],text=True)
   self.assertIn('192.0.2.5',text);self.assertIn('2001:DB8',text)
   state=root/'etc/serviceready/tls/addresses.json';before=state.stat().st_mtime_ns
   openwrt_tls.refresh(config,addresses,root=root,reload=False)
   self.assertEqual(state.stat().st_mtime_ns,before)
   conf=(root/'etc/serviceready/nginx.conf').read_text();self.assertIn('worker_processes 1',conf);self.assertIn('user serviceready serviceready',conf)
 def test_menu_rejects_bad_interface_before_uci(self):
  menu=load('ow_menu','deploy/openwrt/menu-apply.py')
  with patch.object(menu,'run') as run:
   with self.assertRaises(ValueError):menu.network('lan;reboot','dhcp','','','')
   run.assert_not_called()
class PackagingTests(unittest.TestCase):
 def test_runtime_profile_persistent_state_and_small_defaults(self):
  c=bootstrap.configuration();self.assertTrue(c['database'].startswith('/etc/'));self.assertEqual(c['server_threads'],2);self.assertEqual(c['connection_limit'],32);self.assertTrue(c['first_boot_setup']);self.assertEqual(c['initial_modules'],[])
  self.assertIn('open-vm-tools',image.packages('both'));self.assertIn('kmod-serviceready-vboxguest',image.packages('both'));self.assertNotIn('python3-pip',image.packages('both'))
 def test_overlay_contains_dhcp_console_and_no_admin_secret(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);wheels=root/'wheels';wheels.mkdir()
   for dep in bundle.DEPENDENCIES:
    name,version=dep.split('==')
    with zipfile.ZipFile(wheels/(name+'-'+version+'-py3-none-any.whl'),'w') as z:z.writestr(name+'/__init__.py','# fake dependency for packaging test')
   output=bundle.build(root/'bundle.tar.gz',wheels);destination=root/'overlay';image.overlay(output,destination,'both')
   script=(destination/'etc/uci-defaults/95-serviceready').read_text();self.assertIn("network.lan.proto='dhcp'",script);self.assertIn('bootstrap',script);self.assertTrue((destination/'usr/sbin/insap-setup').exists())
   self.assertFalse((destination/'etc/serviceready/setup-token').exists());self.assertFalse((destination/'opt/serviceready/app/__pycache__').exists())
 def test_ova_descriptor_and_real_disk_conversion(self):
  if not __import__('shutil').which('qemu-img'):self.skipTest('qemu-img only required on image build host')
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);raw=root/'disk.img';raw.write_bytes(b'\0'*(1024*1024));out=ova.build(raw,root/'INSAP.ova')
   with tarfile.open(out) as archive:
    self.assertEqual(archive.getnames(),['insap.ovf','insap.mf','insap.vmdk']);xml=archive.extractfile('insap.ovf').read().decode();self.assertIn('Management',xml);self.assertIn('streamOptimized',xml)
 def test_openwrt_rejects_rocky_updates_before_commands(self):
  with patch('subprocess.run') as run:
   with self.assertRaisesRegex(ValueError,'OpenWrt'):provider.handle({'action':'maintenance-start','username':'os'},Mock())
   run.assert_not_called()
