#!/bin/sh
# Run from a Git checkout as root. Existing configuration and accounts are retained.
set -eu
[ "$(id -u)" = 0 ] || { echo "Run this installer as root." >&2; exit 1; }
[ -f /etc/alpine-release ] || { echo "This installer requires Alpine Linux." >&2; exit 1; }
command -v rc-service >/dev/null || { echo "OpenRC is required; use a normal Alpine VM installation." >&2; exit 1; }
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ -f "$source_dir/pyproject.toml" ] || { echo "Incomplete ServiceReady checkout." >&2; exit 1; }
config_template="$source_dir/config.example.json"
case "${1:-}" in
    --bare) config_template="$source_dir/config.bare.json"
        [ ! -f /etc/serviceready/config.json ] || { echo "Bare installation requires a fresh VM; existing settings are preserved." >&2; exit 1; } ;;
    "") ;;
    *) echo "Usage: $0 [--bare]" >&2; exit 1 ;;
esac
umask 027
apk add --no-cache python3 py3-pip git ca-certificates dnsmasq tzdata
grep -q '^serviceready:' /etc/group || addgroup -S serviceready
id serviceready >/dev/null 2>&1 || adduser -S -D -H -G serviceready -h /var/lib/serviceready -s /sbin/nologin serviceready
mkdir -p /opt/serviceready /etc/serviceready /var/lib/serviceready /var/log/serviceready /var/lib/serviceready/tmp
chown serviceready:serviceready /var/lib/serviceready /var/log/serviceready
chmod 0750 /etc/serviceready /var/lib/serviceready /var/log/serviceready
chown root:serviceready /etc/serviceready
grep -q '^serviceready-users:' /etc/group || addgroup -S serviceready-users
install -m 0700 "$source_dir/deploy/account-broker.py" /opt/serviceready/account-broker.py
install -m 0755 "$source_dir/deploy/serviceready-accounts.initd" /etc/init.d/serviceready-accounts
rc-update add serviceready-accounts default
rc-service serviceready-accounts restart
python3 -m venv /opt/serviceready/venv
/opt/serviceready/venv/bin/pip install --disable-pip-version-check "$source_dir" 'waitress==3.0.2' 'pyftpdlib==2.1.0'
chown root:serviceready /opt/serviceready
chmod 0750 /opt/serviceready
chgrp -R serviceready /opt/serviceready/venv
chmod -R g+rX /opt/serviceready/venv
if [ ! -f /etc/serviceready/config.json ]; then
    printf 'Portal URL (example: http://192.168.10.50:8080): '
    read -r portal_url
    /opt/serviceready/venv/bin/python - "$config_template" "$portal_url" <<'PY'
import json,sys
from urllib.parse import urlsplit
url = sys.argv[2].rstrip('/')
p = urlsplit(url)
if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.query or p.fragment or p.path:
    raise SystemExit('Enter an HTTP(S) origin with no path, username or password.')
with open(sys.argv[1]) as f: config = json.load(f)
config.update(database='/var/lib/serviceready/serviceready.sqlite3',public_url=url,
              secure_cookies=p.scheme=='https',listen_host='0.0.0.0',listen_port=8080,
              auth_backend='alpine',account_socket='/run/serviceready-accounts/socket',
              update_directory='/var/lib/serviceready/updates',addon_directory='/var/lib/serviceready/addons')
with open('/etc/serviceready/config.json','x') as f: json.dump(config,f,indent=2)
PY
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
install -m 0755 "$source_dir/deploy/serviceready-pxe.initd" /etc/init.d/serviceready-pxe
rc-update add serviceready-pxe default
rc-service serviceready-pxe restart
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
PY
