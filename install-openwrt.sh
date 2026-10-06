#!/bin/sh
# Run from an extracted INSAP OpenWrt release bundle, as root.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run as root.' >&2; exit 1; }
[ -f /etc/openwrt_release ] || { echo 'This installer requires OpenWrt.' >&2; exit 1; }
. /etc/openwrt_release
case "$DISTRIB_RELEASE" in 25.12.*) ;; *) echo 'Use the current OpenWrt 25.12 stable series.' >&2; exit 1;; esac
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
port=${1:-443}
case "$port" in ''|*[!0-9]*) echo 'Usage: sh install-openwrt.sh [HTTPS port]' >&2; exit 1;; esac
[ -d "$source_dir/app/voiceservices" ] || { echo 'Download and extract the OpenWrt runtime bundle; a Git checkout alone is not the bundle.' >&2; exit 1; }
[ -f "$source_dir/bundle.json" ] || exit 1
[ ! -e /opt/serviceready/venv ] || { echo 'A full runtime exists here. Back up and migrate to a fresh OpenWrt VM instead.' >&2; exit 1; }
nginx_preexisting=0
[ ! -e /etc/init.d/nginx ] || nginx_preexisting=1
echo '[1/5] Installing runtime packages (no compiler, Git or pip)'
packages=$(sed '/^[[:space:]]*#/d;/^[[:space:]]*$/d' "$source_dir/deploy/openwrt/packages.txt")
# The stable release package manager is used only to add dependencies, never bulk-upgrade firmware.
apk update
apk add $packages
if [ "$nginx_preexisting" = 0 ]; then /etc/init.d/nginx disable; /etc/init.d/nginx stop; fi
[ ! -x /etc/init.d/serviceready-proxy ] || /etc/init.d/serviceready-proxy stop
python3 - "$port" <<'PY'
import socket,sys
port=int(sys.argv[1]);assert 1<=port<=65535
with socket.socket() as server:
 try:server.bind(('0.0.0.0',port))
 except OSError:raise SystemExit('HTTPS port is already in use. Move the existing service or choose another portal port.')
PY
echo '[2/5] Installing the prebuilt Python application'
mkdir -p /opt/serviceready
for service in serviceready serviceready-proxy serviceready-accounts; do
 [ ! -x "/etc/init.d/$service" ] || "/etc/init.d/$service" stop
done
[ ! -e /opt/serviceready/app.new ] || { echo "Remove the incomplete app.new staging directory before retrying." >&2; exit 1; }
cp -R "$source_dir/app" /opt/serviceready/app.new
rm -rf /opt/serviceready/app.previous
[ ! -d /opt/serviceready/app ] || mv /opt/serviceready/app /opt/serviceready/app.previous
mv /opt/serviceready/app.new /opt/serviceready/app
cp "$source_dir/deploy/account-broker.py" /opt/serviceready/account-broker.py
cp "$source_dir/deploy/openwrt/host-provider.py" /opt/serviceready/openwrt-host.py
cp "$source_dir/deploy/openwrt/bootstrap.py" /opt/serviceready/openwrt-bootstrap.py
cp "$source_dir/deploy/openwrt/menu.sh" /opt/serviceready/openwrt-menu.sh
cp "$source_dir/deploy/openwrt/menu-apply.py" /opt/serviceready/openwrt-menu.py
mkdir -p /usr/sbin
printf '#!/bin/sh\nexec sh /opt/serviceready/openwrt-menu.sh "$@"\n' > /usr/sbin/insap-setup
chmod 0755 /usr/sbin/insap-setup
chmod -R go-w /opt/serviceready
for service in serviceready serviceready-accounts serviceready-proxy; do
 cp "$source_dir/deploy/openwrt/$service.init" "/etc/init.d/$service"
 chmod 0755 "/etc/init.d/$service"
done
echo '[3/5] Preparing persistent settings and local HTTPS'
export PYTHONPATH=/opt/serviceready/app
python3 /opt/serviceready/openwrt-bootstrap.py --port "$port"
echo '[4/5] Starting the portal'
for service in serviceready-accounts serviceready serviceready-proxy; do "/etc/init.d/$service" start; done
echo '[5/5] Verifying the portal'
python3 - <<'PY'
import time,urllib.request
for attempt in range(20):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=2) as response:assert response.status==200
  break
 except OSError:time.sleep(1)
else:raise SystemExit('Portal did not become healthy. Inspect logread -e serviceready; previous app is retained as app.previous.')
PY
rm -rf /opt/serviceready/app.previous
echo 'Open the VM DHCP address using HTTPS. Trust /etc/serviceready/tls/ca.crt on your browser machine.'
echo 'The first-boot wizard uses the setup code displayed on the VM console.'
