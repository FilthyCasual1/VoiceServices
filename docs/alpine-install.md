# ServiceReady on Alpine / ESXi

Use an installed Alpine Linux x86_64 VM with OpenRC and a persistent disk.
Attach its virtual NIC to a port group reachable from your phones and testbed
services. Give the VM a stable address. The installer does not change ESXi,
network configuration, firewall rules, or external applications.

As root on the VM:

```sh
apk add --no-cache git ca-certificates
git clone --branch initial-portal https://github.com/FilthyCasual1/VoiceServices.git
cd VoiceServices
sh install-alpine.sh
```

The work currently lives on `initial-portal`. Once merged, use the repository's
main branch instead. Fresh installs authenticate against enrolled Alpine accounts through a local privileged broker. The installer prompts for the browser-facing URL, then the
first administrator username and password (12 characters minimum). It does not
install the local preview's admin/admin account. For an isolated HTTP testbed,
use a URL such as `http://192.168.10.50:8080`. Browse that URL and sign in.

The installed server listens on port 8080 on all interfaces and starts on boot. Administration > Addons controls the optional Voice Services, Server Management and FTP Update Repository modules. The FTP worker is installed but opens no ports until the addon is installed, configured and enabled.
For HTTPS, place a TLS reverse proxy in front of it and supply its external HTTPS
URL; restrict port 8080 to the proxy. Waitress does not terminate TLS itself.
HTTP installations use non-Secure cookies; HTTPS configurations use Secure
cookies. Phone Services URLs use the configured public URL.

## Files and management

- `/etc/serviceready/config.json`: public URL, phone setup details, application
  links, installer links, database path and `listen_host` / `listen_port`.
- `/var/lib/serviceready/serviceready.sqlite3`: accounts, contacts, plugin packages
  and settings. Back up this directory with the service stopped.
- `/opt/serviceready/venv`: installed package, Waitress 3.0.2 and pyftpdlib 2.1.0.
- `/var/log/serviceready/service.log` and `error.log`: service output; request
  targets are not access-logged by this server.

```sh
rc-service serviceready status
rc-service serviceready restart
rc-service serviceready stop
```

Edit configuration, then restart the service. Configure the native application
URLs, provisioning details and client download URLs in the configuration file.
The portal exposes links and setup instructions; live provisioning, roaming,
recording and external provider integrations remain future development.

## Updating

```sh
cd VoiceServices
git pull --ff-only
sh install-alpine.sh
```

Rerunning upgrades the installed package and restarts the service while retaining
configuration and database contents. Back up the database and config first. If
package installation or setup fails, correct the reported error and rerun.
The installer uses fixed installation paths, requires root, and downloads Python
packages from PyPI. Logs are not rotated automatically; add a rotation policy
for a longer-lived testbed.

## Validation boundary

The Python test suite and shell syntax checks pass. Package installation, static assets and Waitress HTTP startup were verified in an isolated Python environment. Alpine container validation was blocked by this workspace's user-namespace restrictions. The
installer also performs a local HTTP health check after startup. A live ESXi VM
and integration with external communications applications have not been tested.

See [Modules, system accounts and update files](modules-and-accounts.md) for enrollment, migration and addon controls. The installer places request temporary files on persistent disk under `/var/lib/serviceready/tmp`.
