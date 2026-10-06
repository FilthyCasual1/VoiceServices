#!/bin/sh
# Run from a Git checkout as root. Existing configuration and accounts are retained.
set -eu
[ "$(id -u)" = 0 ] || { echo "Run this installer as root." >&2; exit 1; }
[ -f /etc/alpine-release ] || { echo "This installer requires Alpine Linux." >&2; exit 1; }
command -v rc-service >/dev/null || { echo "OpenRC is required; use a normal Alpine VM installation." >&2; exit 1; }
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ -f "$source_dir/pyproject.toml" ] || { echo "Incomplete ServiceReady checkout." >&2; exit 1; }
config_template="$source_dir/config.bare.json"
local_tls=0
for option in "$@"; do
    case "$option" in
        --bare) [ ! -f /etc/serviceready/config.json ] || { echo "Bare installation requires a fresh VM; existing settings are preserved." >&2; exit 1; } ;;
        --tls) local_tls=1 ;;
        *) echo "Usage: $0 [--bare] [--tls]" >&2; exit 1 ;;
    esac
done
# An existing reverse proxy belongs to its administrator; never overwrite it.
if [ "$local_tls" = 1 ]; then
    [ ! -f /etc/caddy/Caddyfile ] || { echo "Caddy is already configured. Keep your reverse proxy and rerun without --tls." >&2; exit 1; }
fi
export SERVICEREADY_LOCAL_TLS="$local_tls"
umask 027
apk add --no-cache python3 py3-pip git ca-certificates dnsmasq tzdata krb5 krb5-dev build-base python3-dev iproute2
grep -q '^serviceready:' /etc/group || addgroup -S serviceready
id serviceready >/dev/null 2>&1 || adduser -S -D -H -G serviceready -h /var/lib/serviceready -s /sbin/nologin serviceready
mkdir -p /opt/serviceready /etc/serviceready /var/lib/serviceready /var/log/serviceready /var/lib/serviceready/tmp
chown serviceready:serviceready /var/lib/serviceready /var/log/serviceready
chmod 0750 /etc/serviceready /var/lib/serviceready /var/log/serviceready
chown root:serviceready /etc/serviceready
grep -q '^serviceready-users:' /etc/group || addgroup -S serviceready-users
install -m 0700 "$source_dir/deploy/maintenance-worker.py" /opt/serviceready/maintenance-worker.py
if [ ! -d /opt/serviceready/source ]; then
    git clone --branch main https://github.com/FilthyCasual1/VoiceServices.git /opt/serviceready/source
    git -C /opt/serviceready/source remote set-url origin https://github.com/FilthyCasual1/VoiceServices.git
    chmod -R go-w /opt/serviceready/source
fi
install -m 0700 "$source_dir/deploy/account-broker.py" /opt/serviceready/account-broker.py
install -m 0755 "$source_dir/deploy/serviceready-accounts.initd" /etc/init.d/serviceready-accounts
rc-update add serviceready-accounts default
rc-service serviceready-accounts restart
python3 -m venv /opt/serviceready/venv
/opt/serviceready/venv/bin/pip install --disable-pip-version-check "$source_dir[identity]" 'waitress==3.0.2' 'pyftpdlib==2.1.0' 'aiosmtpd==1.4.6'
chown root:serviceready /opt/serviceready
chmod 0750 /opt/serviceready
chgrp -R serviceready /opt/serviceready/venv
chmod -R g+rX /opt/serviceready/venv
if [ ! -f /etc/serviceready/config.json ]; then
    printf 'Portal URL (Enter = automatically follow this machine’s address): '
    read -r portal_url
    /opt/serviceready/venv/bin/python - "$config_template" "$portal_url" <<'PY'
import json,sys,os
from urllib.parse import urlsplit
from voiceservices.network_address import Addresses,origin
local_tls = os.environ.get('SERVICEREADY_LOCAL_TLS') == '1'
automatic = not sys.argv[2].strip()
url = sys.argv[2].strip().rstrip('/')
if automatic:
    _,address=Addresses().current()
    if not address:raise SystemExit('No active network address found. Configure networking and rerun.')
    url=origin({'public_url':'https://localhost' if local_tls else 'http://localhost:8080'},address)
p = urlsplit(url)
if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.query or p.fragment or p.path:
    raise SystemExit('Enter an HTTP(S) origin with no path, username or password.')
local_tls = os.environ.get('SERVICEREADY_LOCAL_TLS') == '1'
if local_tls and (p.scheme != 'https' or p.port not in (None,443)):
    raise SystemExit('--tls requires an https:// hostname or IP on port 443.')
with open(sys.argv[1]) as f: config = json.load(f)
config.update(automatic_public_url=automatic,automatic_local_tls=automatic and local_tls,database='/var/lib/serviceready/serviceready.sqlite3',public_url=url,
              secure_cookies=p.scheme=='https',listen_host='127.0.0.1' if local_tls else '0.0.0.0',listen_port=8080,
              auth_backend='alpine',account_socket='/run/serviceready-accounts/socket',
              update_directory='/var/lib/serviceready/updates',addon_directory='/var/lib/serviceready/addons')
with open('/etc/serviceready/config.json','x') as f: json.dump(config,f,indent=2)
PY
fi
if [ "$local_tls" = 1 ]; then
    apk add --no-cache caddy caddy-openrc
    /opt/serviceready/venv/bin/python - <<'PYTLS'
import json,ipaddress
from pathlib import Path
from urllib.parse import urlsplit
config=json.loads(Path('/etc/serviceready/config.json').read_text())
p=urlsplit(config['public_url'])
if p.scheme!='https' or p.port not in (None,443):raise SystemExit('--tls requires HTTPS on port 443.')
# Restrict generated Caddy syntax to a hostname or literal IP.
host=p.hostname
try:ipaddress.ip_address(host)
except ValueError:
    import re
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*',host):raise SystemExit('Invalid TLS hostname.')
address='['+host+']' if ':' in host else host
config.update(listen_host='127.0.0.1',secure_cookies=True)
Path('/etc/serviceready/config.json').write_text(json.dumps(config,indent=2))
Path('/etc/caddy/Caddyfile').write_text('https://'+address+' {\n    tls internal\n    reverse_proxy 127.0.0.1:'+str(config.get('listen_port',8080))+'\n}\n')
if config.get('automatic_public_url'):
    from voiceservices.network_address import Addresses,caddy_config
    values,primary=Addresses().current()
    if not primary:raise SystemExit('No active network address found.')
    Path('/etc/caddy/Caddyfile').write_text(caddy_config(values,primary,config.get('listen_port',8080)))
PYTLS
    chmod 0644 /etc/caddy/Caddyfile
    caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
    rc-update add caddy default
    rc-service caddy restart
fi
chown root:serviceready /etc/serviceready/config.json
chmod 0640 /etc/serviceready/config.json
has_admin=$(/opt/serviceready/venv/bin/python - <<'PY'
import json
from voiceservices.core import Store
with open('/etc/serviceready/config.json') as f: config = json.load(f)
with Store(config['database']).connect() as db:
    print(int(db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone() is not None))
PY
)
if [ "$has_admin" = 0 ]; then
    printf 'First administrator username: '
    read -r admin_name
    /opt/serviceready/venv/bin/python -m voiceservices --config /etc/serviceready/config.json create-user "$admin_name" --admin
fi
chown -R serviceready:serviceready /var/lib/serviceready
install -m 0755 "$source_dir/deploy/serviceready.initd" /etc/init.d/serviceready
install -m 0755 "$source_dir/deploy/serviceready-ftp.initd" /etc/init.d/serviceready-ftp
rc-update add serviceready-ftp default
rc-service serviceready-ftp restart
install -m 0755 "$source_dir/deploy/serviceready-smtp.initd" /etc/init.d/serviceready-smtp
rc-update add serviceready-smtp default
rc-service serviceready-smtp restart
install -m 0755 "$source_dir/deploy/serviceready-pxe.initd" /etc/init.d/serviceready-pxe
rc-update add serviceready-pxe default
rc-service serviceready-pxe restart
install -m 0755 "$source_dir/deploy/serviceready-scheduler.initd" /etc/init.d/serviceready-scheduler
rc-update add serviceready-scheduler default
rc-service serviceready-scheduler restart
rc-update add serviceready default
rc-service serviceready restart
/opt/serviceready/venv/bin/python - <<'PY'
import json,time
from urllib.request import urlopen
with open('/etc/serviceready/config.json') as f: config=json.load(f)
host=config.get('listen_host','0.0.0.0')
if host=='0.0.0.0': host='127.0.0.1'
for attempt in range(20):
    try:
        with urlopen(f"http://{host}:{config.get('listen_port',8080)}/healthz",timeout=2) as r:
            assert json.load(r)['status']=='running'
        break
    except Exception:
        if attempt==19: raise
        time.sleep(.5)
print('ServiceReady is running: '+config['public_url'])
print('Config: /etc/serviceready/config.json | Logs: /var/log/serviceready/')
if config['public_url'].startswith('https:'):
    print('HTTPS: trust your proxy certificate on client machines before signing in.')
PY

install -m 0755 "$source_dir/deploy/serviceready-snmp.initd" /etc/init.d/serviceready-snmp
rc-update add serviceready-snmp default
rc-service serviceready-snmp restart

install -m 0755 "$source_dir/deploy/serviceready-addresses.initd" /etc/init.d/serviceready-addresses
rc-update add serviceready-addresses default
rc-service serviceready-addresses restart
