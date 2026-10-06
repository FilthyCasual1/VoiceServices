#!/bin/bash
# Persistent Rocky 10 VM installer. Run from the main-branch checkout as root.
set -euo pipefail
stage=preflight
trap 'code=$?; if (( code != 0 )); then echo "Installation incomplete during $stage. See /var/log/serviceready-install.log and journalctl -u serviceready -u nginx." >&2; fi' EXIT
[[ $(id -u) == 0 ]] || { echo 'Run as root (sudo bash install-rocky.sh).'; exit 1; }
source /etc/os-release
[[ $ID == rocky && ${VERSION_ID%%.*} == 10 ]] || { echo 'This installer targets Rocky Linux 10.'; exit 1; }
[[ -d /run/systemd/system ]] || { echo 'Use an installed Rocky VM running systemd.'; exit 1; }
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
use_menu=1
manage_firewall=1
selected_addons=""
portal_url=""
for argument in "$@"; do
    case "$argument" in --bare|--tls) ;; --no-menu) use_menu=0 ;; *) echo 'Usage: bash install-rocky.sh [--bare] [--tls] [--no-menu]'; exit 1;; esac
done
umask 027
log=/var/log/serviceready-install.log
[[ ! -L $log ]] || { echo 'Installer log must not be a symlink.'; exit 1; }
touch "$log"; chmod 0600 "$log"
source "$source_dir/deploy/rocky-progress.sh"
[[ ! -f /etc/nginx/conf.d/serviceready.conf ]] || grep -q '^# ServiceReady managed nginx configuration$' /etc/nginx/conf.d/serviceready.conf || { echo 'Existing Nginx portal configuration is not installer-managed.'; exit 1; }
step 'Official repositories and dependency preflight'
run dnf -y install dnf-plugins-core newt
run dnf config-manager --set-enabled crb
if [[ $use_menu == 1 ]]; then
    [[ -t 0 && -t 1 ]] || { echo 'Use a terminal for the menu, or --no-menu for console prompts.'; exit 1; }
    if [[ -f /etc/serviceready/config.json ]]; then
        portal_url=$(python3 -c 'import json; c=json.load(open("/etc/serviceready/config.json")); print("" if c.get("automatic_public_url") else c.get("public_url",""))')
        selected_addons=$(python3 -c 'import json; from pathlib import Path; c=json.load(open("/etc/serviceready/config.json")); p=Path(c.get("addon_directory","/var/lib/serviceready/addons")); print("\n".join(d.name for d in p.iterdir() if d.is_dir() and d.name != "host-tools"))' 2>/dev/null || true)
    fi
    source "$source_dir/deploy/rocky-menu.sh"
    rocky_menu || { echo 'Setup cancelled; no portal settings or accounts changed.'; exit 0; }
    progress_ui=1
fi
packages=(python3 python3-pip python3-devel gcc make chrony e2fsprogs util-linux NetworkManager krb5-workstation krb5-devel libffi-devel openssl nginx iproute git shadow-utils libxcrypt dnsmasq policycoreutils policycoreutils-python-utils firewalld)
run dnf -y --downloadonly install "${packages[@]}"
step 'Install dependencies'
run dnf -y install "${packages[@]}"
python3 -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ required"'
step 'Portal configuration'
mkdir -p /etc/serviceready
if [[ ! -f /etc/serviceready/config.json ]]; then
    if [[ $use_menu == 0 ]]; then read -r -p 'Portal URL (Enter = follow the current host address): ' portal_url; fi
    PYTHONPATH="$source_dir" run python3 "$source_dir/deploy/rocky-setup.py" config --template "$source_dir/config.bare.json" --url "$portal_url"
else
    echo 'Retaining existing accounts and saved data.'
    if [[ $use_menu == 1 ]]; then PYTHONPATH="$source_dir" run python3 "$source_dir/deploy/rocky-setup.py" config --update --template "$source_dir/config.bare.json" --url "$portal_url"; fi
fi
step 'System accounts and application'
getent group serviceready >/dev/null || groupadd --system serviceready
id serviceready >/dev/null 2>&1 || useradd --system --no-create-home --gid serviceready --home-dir /var/lib/serviceready --shell /sbin/nologin serviceready
getent group serviceready-users >/dev/null || groupadd serviceready-users
mkdir -p /opt/serviceready /var/lib/serviceready/tmp /var/log/serviceready
chown root:serviceready /etc/serviceready /etc/serviceready/config.json /opt/serviceready
chmod 0750 /etc/serviceready /opt/serviceready
chmod 0640 /etc/serviceready/config.json
chown -R serviceready:serviceready /var/lib/serviceready /var/log/serviceready
chmod 0750 /var/lib/serviceready /var/lib/serviceready/tmp /var/log/serviceready
if [[ ! -d /opt/serviceready/source ]]; then
    run git clone --branch main https://github.com/FilthyCasual1/VoiceServices.git /opt/serviceready/source
    chmod -R go-w /opt/serviceready/source
fi
run python3 -m venv /opt/serviceready/venv
run /opt/serviceready/venv/bin/pip install --disable-pip-version-check "$source_dir[identity]" waitress==3.0.2 pyftpdlib==2.1.0 aiosmtpd==1.4.6
chgrp -R serviceready /opt/serviceready/venv; chmod -R g+rX /opt/serviceready/venv
for file in account-broker.py maintenance-worker.py host-control.py; do install -m 0700 "$source_dir/deploy/$file" "/opt/serviceready/$file"; done
for file in "$source_dir"/deploy/systemd/*.service; do install -m 0644 "$file" /etc/systemd/system/; done
run systemctl daemon-reload
run systemctl enable --now serviceready-accounts
step 'First administrator'
has_admin=$(/opt/serviceready/venv/bin/python - <<'PY'
import json
from voiceservices.core import Store
config=json.load(open('/etc/serviceready/config.json'))
with Store(config['database']).connect() as db:print(int(db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone() is not None))
PY
)
if [[ $has_admin == 0 ]]; then
    read -r -p 'New administrator username (do not use an existing OS username): ' admin_name
    /opt/serviceready/venv/bin/python -m voiceservices --config /etc/serviceready/config.json create-user "$admin_name" --admin
fi
chown -R serviceready:serviceready /var/lib/serviceready
if [[ -n $selected_addons ]]; then
    step 'Install selected addon files'
    version=$(/opt/serviceready/venv/bin/python -c 'from voiceservices.version import __version__; print(__version__)')
    while IFS= read -r addon; do
        case "$addon" in downloads|smtp-notifications|snmp|voice|esxi|server-management|ftp-updates|pxe) ;; *) echo "Unknown addon: $addon"; exit 1;; esac
        package="$source_dir/packages/addons/$version/$addon-$version.sraddon"
        if [[ -d /var/lib/serviceready/addons/$addon ]]; then
            run /opt/serviceready/venv/bin/python -m voiceservices --config /etc/serviceready/config.json uninstall-addon "$addon"
        fi
        run /opt/serviceready/venv/bin/python -m voiceservices --config /etc/serviceready/config.json install-addon "$package"
    done <<< "$selected_addons"
    chown -R serviceready:serviceready /var/lib/serviceready
fi
step 'HTTPS proxy and SELinux'
run /opt/serviceready/venv/bin/python "$source_dir/deploy/rocky-setup.py" proxy
if [[ $(getenforce) != Disabled ]]; then run setsebool -P httpd_can_network_connect on; fi
run restorecon -RF /opt/serviceready /var/lib/serviceready /var/log/serviceready /etc/serviceready
run nginx -t
step 'Firewall and services'
if [[ $manage_firewall == 1 ]]; then
    run systemctl enable --now firewalld
    zones=$( { firewall-cmd --get-default-zone; firewall-cmd --get-active-zones | awk '/^[^ ]/{print $1}'; } | sort -u)
    for zone in $zones; do
        run firewall-cmd --zone="$zone" --add-service=https
        run firewall-cmd --permanent --zone="$zone" --add-service=https
    done
fi
run systemctl enable nginx
run systemctl restart nginx
for service in serviceready serviceready-ftp serviceready-smtp serviceready-pxe serviceready-snmp serviceready-scheduler serviceready-addresses; do
    run systemctl enable "$service"
    run systemctl restart "$service"
    run systemctl is-active --quiet "$service"
done
step 'Verify HTTP and HTTPS'
run /opt/serviceready/venv/bin/python "$source_dir/deploy/rocky-setup.py" verify
/opt/serviceready/venv/bin/python -c 'from voiceservices.version import __version__; print(__version__)' > /etc/serviceready/installed-version
/opt/serviceready/venv/bin/python -c 'import json; print("Portal: "+json.load(open("/etc/serviceready/config.json"))["public_url"])'
progress_complete
echo 'Installation complete. Trust /etc/serviceready/tls/ca.crt on browser machines. Never export ca.key.'
echo "Installer log: $log"
