"""Broker policy checks with isolated host-account operations."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch,mock_open

spec=importlib.util.spec_from_file_location('account_broker',Path(__file__).parents[1]/'deploy/account-broker.py')
broker=importlib.util.module_from_spec(spec);spec.loader.exec_module(broker)

class BrokerTests(unittest.TestCase):
    def test_root_and_unenrolled_accounts_cannot_authenticate(self):
        with patch.object(broker.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=0,pw_gid=0)),patch.object(broker.grp,'getgrnam',return_value=SimpleNamespace(gr_mem=['admin'],gr_gid=100)):
            self.assertFalse(broker.eligible('admin'))
        with patch.object(broker.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=1000,pw_gid=100)),patch.object(broker.grp,'getgrnam',return_value=SimpleNamespace(gr_mem=[],gr_gid=200)):
            self.assertFalse(broker.eligible('admin'))
    def test_locked_system_account_and_invalid_password_are_rejected(self):
        with patch.object(broker,'eligible',return_value=True),patch('builtins.open',mock_open(read_data='admin:!locked:20000:0:99999:7:::\n')):
            self.assertFalse(broker.authenticate('admin','password'))
        with patch.object(broker,'authenticate',return_value=False),patch.object(broker.subprocess,'run') as run:
            with self.assertRaises(ValueError): broker.handle({'action':'change','username':'admin','password':'wrong','new_password':'new-long-password'})
            run.assert_not_called()
    def test_password_update_passes_secret_on_stdin_and_never_shell(self):
        with patch.object(broker.subprocess,'run') as run:
            broker.set_password('admin','new-long-password')
            self.assertEqual(run.call_args.args[0],['/usr/sbin/chpasswd','-c','SHA512'])
            self.assertEqual(run.call_args.kwargs['input'],'admin:new-long-password\n')
            self.assertNotIn('shell',run.call_args.kwargs)
        with self.assertRaises(ValueError): broker.handle({'action':'create','username':'root;id','password':'new-long-password'})
        with self.assertRaises(ValueError): broker.set_password('admin','bad\npassword-of-length')
