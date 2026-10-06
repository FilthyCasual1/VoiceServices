# Alpine VM installation

Use Alpine Linux x86_64 in **sys (persistent disk) mode**, with OpenRC. This applies to VirtualBox and ESXi. Run `setup-alpine` in the Alpine console, install to the VM disk, reboot, and remove the installation ISO. Ensure the VM has an active network address and working DNS/time synchronization before installing the portal. DHCP and static addresses are supported.

For VirtualBox, a bridged adapter lets other machines reach the portal directly. On an isolated host-only network, add a second NAT adapter for package downloads. Avoid enabling PXE/DHCP on a bridged network that already has a DHCP server. The installer does not change VM networking or firewall rules.

Enable the matching Alpine **community** repository in `/etc/apk/repositories` (the same release as main); Caddy is supplied there.

As root on the VM:

```sh
apk add --no-cache git ca-certificates
git clone --branch main https://github.com/FilthyCasual1/VoiceServices.git
cd VoiceServices
sh install-alpine.sh --bare --tls
```

For this local HTTPS setup, press **Enter** at the URL prompt to follow the current host address, then enter a **new** administrator username and password of at least 12 characters. Choose a username that does not already exist on Alpine. The installer creates an enrolled Alpine account; it does not install the preview's admin/admin credentials. The portal starts bare: Home, accounts, and Administration. Addons are separate uploaded files.

`--tls` installs Caddy with a private local certificate authority, proxies HTTPS to the portal on loopback port 8080, and enables Secure cookies. It refuses to overwrite an existing Caddyfile. Trust the Caddy root certificate on each client using an authenticated copy from the VM; locate it with `find /var/lib/caddy -path '*/pki/authorities/local/root.crt'`. Export **only root.crt**, never private keys. Local certificates are suitable for the testbed; use your organization's certificate for wider deployment. The default advertises the default-route interface address (falling back to another active address). The portal refreshes generated URLs within five seconds; a managed address service refreshes local HTTPS configuration within about fifteen seconds after a DHCP/static address change. Browse the new address after a change and sign in again: browser cookies belong to the old address. No network settings are changed. If you enter an explicit URL instead, it stays fixed and its hostname must resolve to this VM.

If you already manage a TLS reverse proxy, omit `--tls`, enter its external HTTPS URL and restrict port 8080 to that proxy. Plain HTTP without `--tls` works for an isolated testbed, but browser terminal and host cleanup intentionally require HTTPS. Waitress itself does not terminate TLS.

## Addons and first checks

Download matching `.sraddon` files from [the versioned package directory](../packages/addons/1.14.2/) and upload through System > Addons. Host Tools adds Host Maintenance and Host Terminal. Each terminal session requires the signed-in local administrator's Alpine password and runs with that account's OS permissions. New portal accounts have no sudo/doas privileges; grant deliberate host permissions separately if needed. See [Host Tools](host-tools.md).

After installation:

```sh
rc-service serviceready status
rc-service serviceready-accounts status
rc-service caddy status  # only with --tls
wget -qO- http://127.0.0.1:8080/healthz
```

Sign in from your browser, check the host overview, install one addon, remove it, and confirm its menu disappears. Reboot the VM and verify services and installed addons persist. FTP, SMTP, SNMP and PXE workers open no listeners until their addon is installed and configured. Configure them only on appropriate testbed interfaces.

## Files and management

- `/etc/serviceready/config.json`: external portal URL, listener, account broker and data paths; root-owned, readable by the service group.
- `/var/lib/serviceready/`: SQLite database, addon files and uploaded content. Back up alongside configuration; stop services for a complete consistent filesystem backup.
- `/opt/serviceready/source`: root-owned main-branch checkout used by portal updates.
- `/opt/serviceready/venv`: installed Python application and dependencies.
- `/var/log/serviceready/`: portal service and error logs.
- `serviceready-addresses`: follows host address changes for automatic local HTTPS; leaves manually edited Caddyfiles alone.
- `/etc/caddy/Caddyfile` and `/var/lib/caddy/`: local HTTPS configuration and certificate authority, when selected. Back these up securely.

```sh
rc-service serviceready restart
rc-service serviceready stop
```

Use a new administrator account for the portal instead of reusing root. The application runs as the unprivileged serviceready service user; the peer-restricted broker handles enrolled accounts and fixed maintenance tasks. External identity providers are disabled until configured. Set account recovery, session security, timezone and backups before opening access to other users.

## Updating

```sh
cd VoiceServices
git pull --ff-only
sh install-alpine.sh
```

Omit `--bare` and `--tls` on reruns. Existing configuration, accounts, Caddy configuration and saved data are retained. Back up first. The System update interface uses the approved main branch and backs up configuration/database before updating. Installer reruns do not automatically replace installed addon files; upload current matching packages when upgrading addon functionality. No automatic rollback or reboot is performed.

## Validation boundary

Python tests, installer syntax and generated configuration are checked locally. The local development preview runs on Fedora and has no Alpine account broker. A real Alpine/OpenRC installation, private-CA certificate trust, OS account switching and reboot persistence still need validation in your VM. Report installer errors with the failed step and service error log, keeping passwords and private keys out of shared output.

Local HTTPS setup follows the [Alpine Caddy instructions](https://wiki.alpinelinux.org/wiki/Caddy) and [Caddy internal TLS documentation](https://caddyserver.com/docs/caddyfile/directives/tls).
