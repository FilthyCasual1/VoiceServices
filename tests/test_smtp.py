import smtplib,socket,tempfile,unittest
from types import SimpleNamespace
from voiceservices.web import App
from addon_support import install

class SMTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=App({'database':self.tmp.name+'/db','secure_cookies':False})
        self.app.store.create_user('alice','a-long-password');self.app.store.create_user('bob','a-long-password')
        install(self.app,'smtp-notifications');self.module=self.app.modules.load('smtp-notifications')
        self.module.admin_change(self.app,{'host':'127.0.0.1','port':'2525','allowed':'127.0.0.1/32','routes':'alerts@test.local | alice','enabled':'yes'},[])
        self.gateway=self.module.Gateway(self.app,self.module.settings(self.app))
    def tearDown(self): self.tmp.cleanup()
    def test_real_smtp_inbox_delivery_and_uninstall(self):
        from aiosmtpd.controller import Controller
        with socket.socket() as sock: sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        controller=Controller(self.gateway,hostname='127.0.0.1',port=port,data_size_limit=1024*1024)
        controller.start()
        try:
            with smtplib.SMTP('127.0.0.1',port) as client:
                with self.assertRaises(smtplib.SMTPRecipientsRefused): client.sendmail('app@test.local',['unknown@test.local'],'Subject: No\r\n\r\nNo')
                client.sendmail('app@test.local',['alerts@test.local'],'Subject: Important\r\nX-Priority: 1\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nCheck service')
            with self.app.store.connect() as db:
                notice=db.execute("SELECT * FROM notifications WHERE title='Important'").fetchone();self.assertEqual(notice['priority'],'urgent')
                alice=db.execute("SELECT id FROM users WHERE username='alice'").fetchone()[0];self.assertEqual(notice['user_id'],alice)
            self.app.modules.change('smtp-notifications',False)
            with smtplib.SMTP('127.0.0.1',port) as client:
                with self.assertRaises(smtplib.SMTPSenderRefused): client.sendmail('app@test.local',['alerts@test.local'],'Subject: No\r\n\r\nNo')
        finally: controller.stop()
    def test_untrusted_source_and_invalid_route(self):
        self.assertFalse(self.gateway.trusted(SimpleNamespace(peer=('192.0.2.1',123))))
        with self.assertRaises(ValueError): self.module.admin_change(self.app,{'routes':'bad | missing'},[])
        body=self.module.admin_render(self.app,{'csrf':'test'},[])
        self.assertNotIn('Relay',body)
