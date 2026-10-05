"""Portal-wide timezone and safe preset date/time presentation."""
from datetime import datetime
from zoneinfo import ZoneInfo
import json
DATE_FORMATS={'iso':('%Y-%m-%d','YYYY-MM-DD'),'day-first':('%d/%m/%Y','DD/MM/YYYY'),'month-first':('%m/%d/%Y','MM/DD/YYYY'),'named':('%d %b %Y','DD Mon YYYY')}
TIME_FORMATS={'24-hour':('%H:%M','24-hour (HH:MM)'),'24-seconds':('%H:%M:%S','24-hour with seconds'),'12-hour':('%I:%M %p','12-hour (AM/PM)'),'12-seconds':('%I:%M:%S %p','12-hour with seconds')}
def settings(app):
    value=app.config.get('branding',{})
    with app.store.connect() as db:
        row=db.execute("SELECT value FROM portal_settings WHERE key='branding'").fetchone()
        if row: value=json.loads(row[0])
    return {'timezone':value.get('global_timezone',value.get('greeting_timezone','UTC')),'date_format':value.get('date_format','iso'),'time_format':value.get('time_format','24-hour')}
def zone(app): return ZoneInfo(settings(app)['timezone'])
def format_timestamp(app,timestamp,tz=None):
    s=settings(app);value=datetime.fromtimestamp(timestamp,ZoneInfo(tz or s['timezone']))
    return value.strftime(DATE_FORMATS[s['date_format']][0]+' '+TIME_FORMATS[s['time_format']][0]+' %Z')
