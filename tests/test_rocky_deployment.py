import importlib.util,json,os,ssl,socket,subprocess,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from voiceservices import rocky_tls
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('rocky_setup',ROOT/'deploy/rocky-setup.py');setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)
class RockyDeploymentTests(unittest.TestCase):
    def test_config_auto_address_and_system_accounts(self):
        with patch.object(setup.Addresses,'current',return_value=(['10.0.2.3'],'10.0.2.3')):
            config=setup.configuration('',ROOT/'config.bare.json')
            self.assertEqual(config['public_url'],'https://10.0.2.3');self.assertEqual(config['auth_backend'],'system')
            self.assertEqual(config['tls_proxy'],'nginx');self.assertEqual(config['trusted_proxy'],'127.0.0.1');self.assertEqual(config['initial_modules'],[])
            self.assertEqual(config['listen_host'],'127.0.0.1');self.assertTrue(config['secure_cookies'])
            for url in ['http://10.0.2.3','https://10.0.2.3:8080','https://host/path']:
                with self.assertRaises(ValueError):setup.configuration(url,ROOT/'config.bare.json')
    def test_certificate_verified_ip_handshake_and_address_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);addresses=Mock();addresses.current.return_value=(['10.0.2.3'],'10.0.2.3')
            config={'public_url':'https://10.0.2.3'}
            rocky_tls.configure(config,addresses,False,root)
            ca=root/'etc/serviceready/tls/ca.crt';cert=root/'etc/pki/tls/certs/serviceready.crt';key=root/'etc/pki/tls/private/serviceready.key'
            original_ca=ca.read_bytes();self.assertEqual(key.stat().st_mode&0o777,0o600)
            server_context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);server_context.load_cert_chain(cert,key)
            seen=[];server_context.set_servername_callback(lambda sock,name,context:seen.append(name))
            listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
            def serve():
                connection,_=listener.accept()
                with server_context.wrap_socket(connection,server_side=True) as stream:stream.sendall(b'OK')
            thread=threading.Thread(target=serve);thread.start()
            try:
                context=ssl.create_default_context(cafile=str(ca))
                with socket.create_connection(listener.getsockname()) as raw:
                    with context.wrap_socket(raw,server_hostname='10.0.2.3') as stream:self.assertEqual(stream.recv(2),b'OK')
            finally:thread.join(timeout=5);listener.close()
            self.assertEqual(seen,[None]) # Browsers accessing an IP omit DNS SNI.
            addresses.current.return_value=(['10.0.2.4'],'10.0.2.4');config['public_url']='https://10.0.2.4'
            rocky_tls.configure(config,addresses,False,root)
            self.assertEqual(ca.read_bytes(),original_ca)
            result=subprocess.run(['openssl','verify','-CAfile',str(ca),'-verify_ip','10.0.2.4',str(cert)],capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
    def test_rocky_account_commands(self):
        import test_account_broker
        with patch.object(test_account_broker.broker.os.path,'isfile',return_value=True):
            self.assertEqual(test_account_broker.broker.account_command('create','alice'),['/usr/sbin/useradd','-M','-s','/sbin/nologin','-g','serviceready-users','alice'])
            self.assertEqual(test_account_broker.broker.account_command('delete','alice'),['/usr/sbin/userdel','alice'])
    def test_menu_apply_and_cancel(self):
        for cancel in (False,True):
            with self.subTest(cancel=cancel),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);fake=root/'whiptail';counter=root/'counter'
                fake.write_text('#!/bin/bash\nn=$(cat "$COUNTER" 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > "$COUNTER"\n'+('exit 1\n' if cancel else 'case "$n" in 1) echo firewall >&2;; 2) exit 1;; 3) echo addons >&2;; 4) printf "downloads\\nhost-tools\\n" >&2;; 5) echo install >&2;; 6) exit 0;; *) exit 1;; esac\n'))
                fake.chmod(0o755)
                script='source "$1"; VERSION_ID=10; if rocky_menu; then printf "APPLY:%s:%s\\n" "$manage_firewall" "$selected_addons"; else echo CANCEL; fi'
                result=subprocess.run(['bash','-c',script,'menu',str(ROOT/'deploy/rocky-menu.sh')],env=dict(os.environ,PATH=str(root)+':'+os.environ['PATH'],COUNTER=str(counter)),capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                if cancel:self.assertIn('CANCEL',result.stdout)
                else:self.assertIn('APPLY:0:downloads\nhost-tools',result.stdout)
