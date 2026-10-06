#!/bin/bash
# Repair runtime permissions after older GUI updates; preserve configuration/data.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run sudo bash repair-rocky.sh'; exit 1; }
source /etc/os-release
[[ $ID == rocky && ${VERSION_ID%%.*} == 10 ]] || { echo 'Rocky Linux 10 required.'; exit 1; }
source_dir=$(cd -- "$(dirname -- "$0")" && pwd)
echo 'Repairing portal runtime access and verifying imports as the service account…'
install -m 0700 "$source_dir/deploy/admin-reset.py" /usr/local/sbin/serviceready-admin-reset
if ! python3 "$source_dir/deploy/runtime-access.py"; then
    echo 'Runtime imports still fail; reinstalling the portal package from this checkout…'
    /opt/serviceready/venv/bin/pip install --disable-pip-version-check --force-reinstall --no-deps "$source_dir"
    python3 "$source_dir/deploy/runtime-access.py"
fi
echo 'Restoring access to addon files left private by older updates…'
systemctl stop serviceready
python3 - "$source_dir" <<'PYFIX'
import importlib.util,json,pathlib,sys
spec=importlib.util.spec_from_file_location('runtime_access',pathlib.Path(sys.argv[1])/'deploy/runtime-access.py');access=importlib.util.module_from_spec(spec);spec.loader.exec_module(access)
access.normalise_addons(json.load(open('/etc/serviceready/config.json')))
PYFIX
echo 'Installing corrected host workers…'
install -m 0700 "$source_dir/deploy/admin-reset.py" /usr/local/sbin/serviceready-admin-reset
for file in account-broker.py maintenance-worker.py host-control.py runtime-access.py vm-tools.py; do
    install -m 0700 "$source_dir/deploy/$file" "/opt/serviceready/$file"
done
# The missing module was caused by inaccessible runtime files. No reinstall or data reset is needed.
systemctl reset-failed serviceready
systemctl restart serviceready serviceready-accounts
echo 'Waiting for the portal to finish starting…'
for attempt in {1..30}; do
    if /opt/serviceready/venv/bin/python - <<'PY'
from urllib.request import urlopen
from urllib.error import URLError
import json,sys
port=json.load(open('/etc/serviceready/config.json')).get('listen_port',8080)
try:
    with urlopen('http://127.0.0.1:'+str(port)+'/healthz',timeout=2) as response:
        sys.exit(0 if response.status==200 else 1)
except (URLError, TimeoutError, ConnectionError):
    sys.exit(1)
PY
    then
        echo 'Portal recovered. Refresh your browser. Install the latest INSAP release using the GUI when ready.'
        exit 0
    fi
    sleep 1
done
echo 'The portal still cannot start. Last service messages:' >&2
journalctl -u serviceready -n 40 --no-pager
exit 1
