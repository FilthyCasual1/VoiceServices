import unittest,json,socket,threading
from unittest.mock import patch
import test_app
from addon_support import install
class SNMPTests(unittest.TestCase):
    setUp=test_app.PortalTests.setUp
    tearDown=test_app.PortalTests.tearDown
    request=test_app.PortalTests.request
    user=test_app.PortalTests.user
    def addon(self):
        install(self.app,'snmp');return self.app.modules.load('snmp')
    def test_trap_filtering_and_inform_ack(self):
        a=self.addon();s=a.settings(self.app);s.update(community='test',allowed='127.0.0.1/32')
        bindings=[('1.3.6.1.2.1.1.3.0',a.tlv(67,b'\x01')),('1.3.6.1.6.3.1.1.4.1.0',a.tlv(6,a.oid_bytes('1.3.6.1.6.3.1.1.5.1')))]
        packet=a.message('test',166,42,bindings)
        self.assertIsNone(a.receive(self.app,s,packet,('192.0.2.1',1)))
        self.assertIsNone(a.receive(self.app,s,a.message('wrong',167,42,bindings),('127.0.0.1',1)))
        reply=a.receive(self.app,s,packet,('127.0.0.1',1));self.assertEqual(a.decode(reply)[1:4],(162,42,0))
        with self.app.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM snmp_traps').fetchone()[0],1)
        for raw in (b'\x30\x80',b'\x30\x05\x01',b'bad'):
            with self.assertRaises(ValueError):a.decode(raw)
    def test_real_udp_poll_and_permissions(self):
        a=self.addon();oid='1.3.6.1.2.1.1.5.0'
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as agent:
            agent.bind(('127.0.0.1',0));agent.settimeout(3)
            def respond():
                raw,peer=agent.recvfrom(65535);request=a.decode(raw)[2]
                agent.sendto(a.message('test',162,request,[(oid,a.tlv(4,b'Router'))]),peer)
            t=threading.Thread(target=respond);t.start()
            self.assertEqual(a.poll(dict(host='127.0.0.1',port=agent.getsockname()[1],community='test',oids=[oid])),[(oid,'Router')]);t.join()
        admin,user=self.user('admin');alice,_=self.user('alice')
        self.assertEqual(self.request('/admin/snmp',token=alice)['status'],'403 Forbidden')
        self.assertEqual(self.request('/admin/snmp',token=admin)['status'],'200 OK')
        self.app.modules.change('snmp',False)
        self.assertEqual(self.request('/admin/snmp',token=admin)['status'],'404 Not Found')
