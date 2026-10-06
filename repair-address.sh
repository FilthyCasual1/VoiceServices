#!/bin/sh
# Repair an installed portal without reinstalling dependencies or changing accounts.
set -eu
[ "$(id -u)" = 0 ] || { echo "Run as root." >&2; exit 1; }
[ -f /etc/alpine-release ] || { echo "This repair is for the Alpine installation." >&2; exit 1; }
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python=/opt/serviceready/venv/bin/python
[ -x "$python" ] || { echo "Installed portal Python was not found. Run install-alpine.sh first." >&2; exit 1; }
if [ -x /etc/init.d/serviceready-addresses ]; then
    rc-service serviceready-addresses stop
    trap 'rc-service serviceready-addresses start || true' EXIT
fi
PYTHONPATH="$source_dir" "$python" "$source_dir/deploy/repair-address.py"
install -m 0755 "$source_dir/deploy/serviceready-addresses.initd" /etc/init.d/serviceready-addresses
rc-update add serviceready-addresses default
rc-service serviceready-addresses restart
rc-service serviceready restart
trap - EXIT
echo "Address repair complete. Use the URL printed above."
