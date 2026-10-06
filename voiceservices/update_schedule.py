"""Persistent local daily/weekly update schedules, executed by a dedicated worker."""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
import html,json,time
from . import regional
E=lambda v:html.escape(str(v),quote=True)
KINDS={'insap':'Portal release checks','os':'Operating system updates','vmtools':'VM guest tools updates'}
DEFAULT={'enabled':False,'frequency':'weekly','weekday':6,'time':'03:00','timezone':'portal'}
def initialize(app):
    with app.store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS update_schedule_runs(kind TEXT PRIMARY KEY,next_run INTEGER NOT NULL,last_run INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT \'Waiting\',message TEXT NOT NULL DEFAULT \'\')')
        db.execute('CREATE TABLE IF NOT EXISTS scheduler_heartbeat(id INTEGER PRIMARY KEY,at INTEGER NOT NULL)')
def settings(app):
    initialize(app)
    with app.store.connect() as db: row=db.execute("SELECT value FROM portal_settings WHERE key='update_schedules'").fetchone()
    values=json.loads(row[0]) if row else {}
    result={kind:dict(DEFAULT,**values.get(kind,{})) for kind in KINDS}
    for s in result.values(): s['effective_timezone']=regional.settings(app)['timezone'] if s['timezone']=='portal' else s['timezone']
    return result
def next_run(s,now):
    zone=ZoneInfo(s.get('effective_timezone',s['timezone']));local=datetime.fromtimestamp(now,zone);hour,minute=map(int,s['time'].split(':'))
    for offset in range(16):
        day=local.date()+timedelta(days=offset)
        if s['frequency']=='weekly' and day.weekday()!=s['weekday']: continue
        candidate=datetime(day.year,day.month,day.day,hour,minute,tzinfo=zone,fold=0)
        timestamp=int(candidate.timestamp());normalized=datetime.fromtimestamp(timestamp,zone)
        # Skip nonexistent spring-forward times; repeated fall-back times run once.
        if (normalized.hour,normalized.minute)!=(hour,minute): continue
        if timestamp>now: return timestamp
    raise ValueError('Unable to calculate the next schedule occurrence.')
def change(app,user,data):
    if user['role']!='admin': raise PermissionError('Administrator access required.')
    current=settings(app);new={};now=int(time.time())
    for kind in KINDS:
        previous=current[kind];s={}
        s['enabled']=data.get(kind+'_enabled','yes' if previous['enabled'] else 'no')=='yes'
        for key in ('frequency','time','timezone'): s[key]=data.get(kind+'_'+key,previous[key]).strip()
        try:
            s['weekday']=int(data.get(kind+'_weekday',previous['weekday']))
            if s['frequency'] not in ('daily','weekly') or not 0<=s['weekday']<=6: raise ValueError()
            if len(s['time'])!=5 or s['time'][2]!=':': raise ValueError()
            hour,minute=map(int,s['time'].split(':'))
            if not 0<=hour<24 or not 0<=minute<60: raise ValueError()
            s['effective_timezone']=regional.settings(app)['timezone'] if s['timezone']=='portal' else s['timezone']
            ZoneInfo(s['effective_timezone']);next_run(s,now)
        except (ValueError,ZoneInfoNotFoundError): raise ValueError('Choose a daily/weekly schedule, valid time, weekday and IANA time zone.')
        new[kind]=s
    with app.store.connect() as db:
        db.execute("INSERT OR REPLACE INTO portal_settings VALUES('update_schedules',?)",(json.dumps(new),))
        for kind,s in new.items():
            if s!=current[kind] or not db.execute('SELECT 1 FROM update_schedule_runs WHERE kind=?',(kind,)).fetchone():
                db.execute('INSERT INTO update_schedule_runs(kind,next_run) VALUES(?,?) ON CONFLICT(kind) DO UPDATE SET next_run=excluded.next_run,status=\'Waiting\',message=\'Schedule changed\'',(kind,next_run(s,now) if s['enabled'] else 0))
    return 'Update schedules saved.'
def render(app,user):
    schedules=settings(app)
    with app.store.connect() as db:
        rows={r['kind']:dict(r) for r in db.execute('SELECT * FROM update_schedule_runs')};heartbeat=db.execute('SELECT at FROM scheduler_heartbeat WHERE id=1').fetchone()
    text='<p>Run automatic portal, OS and VM guest tools updates separately. Schedules are disabled by default and use the installed host update provider.</p><p>Scheduler: '+('Running' if heartbeat and heartbeat[0]>time.time()-90 else 'Not running or heartbeat unavailable')+'. Host update provider: '+('Configured' if app.store.accounts else 'Unavailable on this deployment')+'.</p><div class="panel"><form method="post" action="/admin/host"><input type="hidden" name="action" value="save-update-schedules"><input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
    for kind,label in KINDS.items():
        s=schedules[kind];text+='<h3>'+label+'</h3><label>Automatic updates</label><select name="'+kind+'_enabled"><option value="no">Off</option><option value="yes"'+(' selected' if s['enabled'] else '')+'>On</option></select><label>Frequency</label><select name="'+kind+'_frequency"><option value="daily">Daily</option><option value="weekly"'+(' selected' if s['frequency']=='weekly' else '')+'>Weekly</option></select><label>Weekday (weekly schedules)</label><select name="'+kind+'_weekday">'+''.join('<option value="'+str(n)+'"'+(' selected' if n==s['weekday'] else '')+'>'+day+'</option>' for n,day in enumerate(('Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday')))+'</select><label>Time</label><input type="time" name="'+kind+'_time" value="'+E(s['time'])+'" required><label>Time zone</label>'+regional.timezone_select(kind+'_timezone',s['timezone'],True)
        row=rows.get(kind,{});due=row.get('next_run',0)
        text+='<p>Next run: '+(E(regional.format_timestamp(app,due,s['effective_timezone'])) if s['enabled'] and due else 'Disabled')+'. Last result: '+E(row.get('status','No runs yet'))+' '+E(row.get('message',''))+'</p>'
    return text+'<button>Save update schedules</button></form></div><p>Scheduled portal checks fetch the release and changelog for review. Installation requires Proceed with update; declined versions stay skipped. Portal installation briefly restarts services and preserves settings. OS updates upgrade installed packages without an automatic reboot. If an update is already running, other due jobs wait. Missed occurrences run once after the scheduler returns; failed requests wait for the next occurrence. Session and security policies remain separate.</p>'
def tick(app,now=None):
    now=int(time.time()) if now is None else int(now);schedules=settings(app)
    with app.store.connect() as db: db.execute('INSERT OR REPLACE INTO scheduler_heartbeat VALUES(1,?)',(now,))
    if not app.store.accounts: return
    state=app.store.accounts.call('maintenance-status','','')
    with app.store.connect() as db:
        if state.get('state') in ('complete','failed'):
            db.execute("UPDATE update_schedule_runs SET status=?,message=? WHERE kind=? AND status='Requested' AND last_run<=?",(state['state'].title(),state.get('message',''),state.get('kind',''),state.get('at',0)))
        recent=db.execute('SELECT MAX(last_run) FROM update_schedule_runs').fetchone()[0] or 0
    if state.get('state')=='running' or recent>now-60: return
    for kind,s in schedules.items():
        if not s['enabled']: continue
        with app.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM update_schedule_runs WHERE kind=?',(kind,)).fetchone()
            if not row:
                db.execute('INSERT INTO update_schedule_runs(kind,next_run) VALUES(?,?)',(kind,next_run(s,now)));continue
            if not row['next_run'] or row['next_run']>now: continue
            recent=db.execute('SELECT MAX(last_run) FROM update_schedule_runs').fetchone()[0] or 0
            if recent>now-60: return
            db.execute("UPDATE update_schedule_runs SET next_run=?,last_run=?,status='Requested',message='Starting scheduled update' WHERE kind=?",(next_run(s,now),now,kind))
        try: app.store.accounts.call('maintenance-start',kind,'')
        except ValueError as exc:
            with app.store.connect() as db: db.execute("UPDATE update_schedule_runs SET status='Failed',message=? WHERE kind=?",(str(exc),kind))
        return

def rebase_global(app):
    schedules=settings(app);now=int(time.time())
    with app.store.connect() as db:
        for kind,s in schedules.items():
            if s['timezone']=='portal':
                db.execute("UPDATE update_schedule_runs SET next_run=?,status='Waiting',message='Global time zone changed' WHERE kind=?",(next_run(s,now) if s['enabled'] else 0,kind))
