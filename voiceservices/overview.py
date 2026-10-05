"""Core portal/system overview using local measurements and worker heartbeats."""
import html,json,os,shutil,socket,time,platform
from pathlib import Path
from .modules import CATALOG
from .version import __version__
E=lambda value:html.escape(str(value),quote=True)

def render(app):
    now=time.time()
    def table(rows): return '<table><tr><th>Item</th><th>Status / details</th></tr>'+''.join('<tr><td>'+E(k)+'</td><td>'+E(v)+'</td></tr>' for k,v in rows)+'</table>'
    usage=shutil.disk_usage(Path(app.store.path).parent)
    resources=[('Portal','Running; version '+__version__),('Host',socket.gethostname()),('Portal uptime',str(int(now-app.started_at))+' seconds'),('Data disk',str(usage.free//1024**2)+' MiB available of '+str(usage.total//1024**2)+' MiB'),('Authentication','Host system accounts' if app.store.accounts else 'Local portal accounts')]
    resources.extend([('Operating system',platform.freedesktop_os_release().get('PRETTY_NAME',platform.system()) if hasattr(platform,'freedesktop_os_release') and Path('/etc/os-release').is_file() else platform.system()),('Kernel',platform.release()),('Architecture',platform.machine()),('Logical CPUs',str(os.cpu_count() or 'Unknown')),('Python',platform.python_version())])
    try:
        cpu=next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith(('model name','Hardware'))),'Unknown')
        resources.append(('Processor',cpu))
    except OSError: pass
    try: resources.append(('System load (1 / 5 / 15 minutes)',' / '.join(f'{v:.2f}' for v in os.getloadavg())))
    except OSError: pass
    try:
        info={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in Path('/proc/meminfo').read_text().splitlines()}
        resources.append(('Host memory',info.get('MemAvailable','Unknown')+' available of '+info.get('MemTotal','Unknown')))
    except OSError: pass
    try: resources.append(('Host uptime',str(int(float(Path('/proc/uptime').read_text().split()[0])))+' seconds'))
    except (OSError,ValueError): pass
    with app.store.connect() as db:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        def count(name,where=''):
            return db.execute('SELECT COUNT(*) FROM '+name+where).fetchone()[0] if name in tables else 0
        resources.extend([('Accounts',str(count('users'))+' total; '+str(count('users'," WHERE role='admin'"))+' administrators'),('Active portal sessions',str(count('sessions',' WHERE expires>'+str(int(now))))),('Enabled home blocks',str(count('home_blocks',' WHERE enabled=1')))])
        statuses={}
        if 'addon_status' in tables:
            statuses={r['id']:(r['status'] if r['at']>now-10 else 'Worker heartbeat stale / unavailable') for r in db.execute('SELECT * FROM addon_status')}
        rows=[]
        for key,(title,_) in CATALOG.items():
            if not app.modules.installed(key): continue
            status='Installed '+app.modules.approved[key]['version']
            if key=='smtp-notifications': status+='; '+statuses.get(key,'Worker unavailable')
            elif key=='downloads': status+='; '+str(count('downloads_files'))+' hosted files; '+str(count('downloads_catalog'))+' catalog links'
            elif key=='pxe':
                status+='; '+str(count('pxe_profiles'))+' profiles; '+str(count('pxe_files'))+' assets'
                setting=app.pxe.settings()
                status+='; '+(statuses.get('pxe','Enabled; worker not verified') if setting['enabled'] else 'Network boot disabled')
            elif key=='ftp-updates':
                setting=app.updates.settings()
                status+='; '+str(count('updates_files'))+' files; '+(statuses.get('ftp-updates','Enabled; worker not verified') if setting and setting.get('enabled') else 'FTP disabled')
            elif key=='voice': status+='; '+str(count('phones',' WHERE expires>'+str(int(now))))+' active application bindings; native phone status unavailable'
            elif key=='esxi':
                raw=db.execute("SELECT value FROM portal_settings WHERE key='esxi'").fetchone()
                host=json.loads(raw[0]).get('host','') if raw else ''
                status+='; '+(host+' configured; connection unverified' if host else 'Host not configured')
            elif key=='server-management': status+='; '+str(sum(bool(v) for v in app.config.get('services',{}).values()))+' configured service links; remote health unverified'
            rows.append((title,status))
    portal_rows=resources[:5]+resources[-3:]
    host_rows=resources[5:-3]
    return '<div class="overview-grid"><section><h2>Portal</h2>'+table(portal_rows)+'</section><section><h2>Host</h2>'+table(host_rows)+'</section><section class="overview-addons"><h2>Installed addons</h2>'+(table(rows) if rows else '<p>No addons installed.</p>')+'</section></div><p class="muted overview-note">Host measurements are local. External service availability is unverified unless reported by an addon.</p>'
