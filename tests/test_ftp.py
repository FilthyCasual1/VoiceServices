import ftplib
import importlib.util
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from voiceservices.core import Store
from voiceservices.updates import Updates

@unittest.skipUnless(importlib.util.find_spec('pyftpdlib'),'Optional FTP dependency not installed')
class FTPTests(unittest.TestCase):
    def test_read_only_transfer_and_addon_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
            config={'database':directory+'/db','update_directory':directory+'/updates','ftp_listen_host':'127.0.0.1'}
            path=Path(directory)/'config.json';path.write_text(json.dumps(config))
            updates=Updates(Store(config['database']),config)
            from addon_support import package
            updates.modules.install(package('ftp-updates'));updates.install()
            updates.configure({'username':'updates','ftp_password':'ftp-testing-password','port':str(port),'passive_start':'31000','passive_end':'31009','enabled':'yes'})
            content=b'example test package';(updates.root/'sample.iso').write_bytes(content)
            process=subprocess.Popen([sys.executable,'-m','voiceservices.ftp_service','--config',str(path)],stderr=subprocess.PIPE)
            try:
                for _ in range(50):
                    try: client=ftplib.FTP();client.connect('127.0.0.1',port,timeout=2);break
                    except OSError: time.sleep(.1)
                else: raise AssertionError('FTP worker failed to start')
                client.login('updates','ftp-testing-password')
                received=[];client.retrbinary('RETR sample.iso',received.append)
                self.assertEqual(b''.join(received),content)
                with self.assertRaises(ftplib.error_perm): client.storbinary('STOR forbidden.iso',io.BytesIO(b'data'))
                client.quit();updates.remove()
                for _ in range(40):
                    try:
                        with socket.create_connection(('127.0.0.1',port),timeout=.2): pass
                    except OSError: break
                    time.sleep(.1)
                else: raise AssertionError('Addon removal left FTP listening')
                self.assertTrue((updates.root/'sample.iso').exists())
            finally:
                process.terminate();_,err=process.communicate(timeout=5)
                if process.returncode not in (0,-15): self.fail(err.decode())
