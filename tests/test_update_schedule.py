from datetime import datetime,timezone
import tempfile,unittest
from unittest.mock import MagicMock
from voiceservices.web import App
from voiceservices import update_schedule
class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=App({'database':self.tmp.name+'/db','secure_cookies':False});self.admin={'role':'admin','csrf':'test'}
    def tearDown(self): self.tmp.cleanup()
    def test_daily_weekly_timezone_and_dst(self):
        s=dict(update_schedule.DEFAULT,frequency='daily',time='03:00',timezone='UTC')
        now=datetime(2026,10,5,2,0,tzinfo=timezone.utc).timestamp()
        self.assertEqual(update_schedule.next_run(s,now),int(now+3600))
        s.update(frequency='weekly',weekday=6)
        self.assertEqual(datetime.fromtimestamp(update_schedule.next_run(s,now),timezone.utc).weekday(),6)
        s.update(time='02:30',timezone='America/Chicago')
        now=datetime(2026,3,8,0,0,tzinfo=timezone.utc).timestamp()
        due=datetime.fromtimestamp(update_schedule.next_run(s,now),__import__('zoneinfo').ZoneInfo(s['timezone']))
        self.assertEqual((due.day,due.hour,due.minute),(15,2,30))
    def test_persistence_disabled_busy_and_once_only(self):
        update_schedule.change(self.app,self.admin,{'insap_enabled':'yes','insap_frequency':'daily','insap_time':'03:00','insap_timezone':'UTC','os_enabled':'yes'})
        self.assertTrue(update_schedule.settings(self.app)['insap']['enabled'])
        self.app.store.accounts=MagicMock();self.app.store.accounts.call.return_value={'state':'running'}
        with self.app.store.connect() as db: db.execute('UPDATE update_schedule_runs SET next_run=100')
        update_schedule.tick(self.app,1000);self.app.store.accounts.call.assert_called_once_with('maintenance-status','','')
        self.app.store.accounts.call.reset_mock();self.app.store.accounts.call.return_value={'state':'idle'}
        update_schedule.tick(self.app,1000);update_schedule.tick(self.app,1000)
        starts=[c for c in self.app.store.accounts.call.call_args_list if c.args[0]=='maintenance-start']
        self.assertEqual(len(starts),1);self.assertEqual(starts[0].args[1],'insap')
        with self.app.store.connect() as db:
            row=db.execute("SELECT * FROM update_schedule_runs WHERE kind='insap'").fetchone();self.assertGreater(row['next_run'],1000);self.assertEqual(row['status'],'Requested')
        update_schedule.change(self.app,self.admin,{'insap_enabled':'no','os_enabled':'no'})
        self.assertFalse(update_schedule.settings(self.app)['insap']['enabled'])
        self.assertIn('Disabled',update_schedule.render(self.app,self.admin))
        with self.assertRaises(ValueError): update_schedule.change(self.app,self.admin,{'os_timezone':'No/SuchZone'})
        with self.assertRaises(PermissionError): update_schedule.change(self.app,{'role':'user'},{})
