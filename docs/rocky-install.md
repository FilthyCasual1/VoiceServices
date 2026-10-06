# Rocky Linux 10 installation

Use a persistent Rocky Linux 10 VM with working networking, DNS and time synchronization. Install Rocky to disk and remove the ISO. Both browser and portal VMs must be on the same VirtualBox NAT Network (or another mutually reachable network). Rocky 10 x86_64 requires an x86-64-v3 capable CPU exposed to the VM.

From the VM console:

```sh
sudo dnf install -y git
git clone --branch main https://github.com/FilthyCasual1/VoiceServices.git
cd VoiceServices
sudo bash install-rocky.sh
```

The installer bootstraps the official DNF tools and `newt`, then opens a **menuconfig-style setup screen**. Use arrows, Space to select addons, Tab to move between buttons, and Enter to choose. Configure the portal address, whether to open HTTPS through firewalld, and addon packages to install/update. Review the summary and confirm Apply. Cancelling does not change portal settings or accounts; bootstrap packages may already be installed.

The default is a bare portal, automatic DHCP/static addressing, and HTTPS on port 443. All addons are unchecked initially. Unchecking an existing addon does not uninstall it; remove addons from the portal. Selected packages are installed from the checkout's matching release. Optional listener configuration and firewall rules are still separate.

If the console cannot display the menu, use `sudo bash install-rocky.sh --no-menu` for text prompts. Compatibility flags `--bare` and `--tls` are accepted; the installer already starts bare with HTTPS. There is no automatic Alpine-to-Rocky account migration. Use a fresh VM rather than copying Alpine system accounts.

## What is installed

- Python 3.12 application environment under `/opt/serviceready/venv`.
- Root-owned main-branch update checkout under `/opt/serviceready/source`.
- Core runs as the unprivileged `serviceready` service user.
- A peer-restricted root broker manages explicitly enrolled local Rocky accounts. New administrator names must not already exist as OS users. Passwords must contain at least 12 characters. Existing root/wheel accounts are not automatically enrolled.
- Systemd services for the portal, broker, address tracking, update scheduling and optional addon supervisors. Uninstalled addons do not open listeners.
- Nginx reverse proxy on HTTPS 443, with the portal bound only to loopback 8080.
- Local certificate authority under `/etc/serviceready/tls/`, and server certificate/key under the standard `/etc/pki/tls/` paths. Certificates include current interface IPs; address changes regenerate the server certificate with the same CA. Leaf certificates renew when less than seven days remain.
- Matching official Rocky BaseOS/AppStream/CRB repositories; no EPEL or COPR repository is required.

SELinux remains enabled. The installer enables `httpd_can_network_connect` so Nginx can proxy to the loopback application and restores file labels. With firewall management selected, it opens only HTTPS in the default and currently active zones. No addon ports are opened automatically. If you turn that option off, configure your existing firewall to allow TCP 443.

## First sign-in

After package installation the console prompts for a new local administrator username and password. Passwords are not written to the installer log. The installer reports success after HTTP and certificate-verified HTTPS health checks. Open the printed URL from the browser VM.

Trust `/etc/serviceready/tls/ca.crt` on browser machines (Windows Trusted Root Certification Authorities; Firefox may need its own Authorities store). Copy it through an authenticated channel. **Never export `ca.key` or the server private key.** This private CA is intended for your testbed; use organization-managed certificates for wider deployment.

Automatic addressing follows the active default-route interface, falling back to another active global address. Generated portal URLs update within five seconds, and proxy certificates/configuration within about fifteen seconds. After changing IP addresses, browse the new address and sign in again because cookies belong to the old address. A manually configured URL remains fixed and must resolve to this VM.

## Management and diagnostics

```sh
sudo systemctl status serviceready serviceready-accounts nginx
sudo journalctl -u serviceready -u serviceready-accounts -u nginx -n 80
sudo journalctl -u serviceready-addresses -n 40
```

Configuration: `/etc/serviceready/config.json`. Data/addons/uploads: `/var/lib/serviceready/`. Installer log: `/var/log/serviceready-install.log`. Nginx configuration: `/etc/nginx/conf.d/serviceready.conf`. Back up these and the private CA securely; a filesystem backup should stop services for consistency.

Rerun from an updated checkout to resume or upgrade:

```sh
git pull --ff-only
sudo bash install-rocky.sh
```

Accounts and saved data are retained. Menu selections can change networking settings; reviewing existing settings does not reset data. Host Tools uses DNF for OS updates/cache cleanup and keeps the administrator's browser shell under their OS UID. New portal accounts have no sudo/wheel privileges unless explicitly granted on the host. OS updates do not reboot automatically.

## Verification boundary

The local test suite checks Rocky configuration, account command selection, menu apply/cancel, systemd unit syntax and real local-CA IP-address TLS handshakes without SNI. The full installer package names were checked against official Rocky 10 repository metadata. This is not proof of a completed Rocky VM installation or SELinux runtime policy behavior: those must be verified on your VM. Keep SELinux enforcing when reporting failures and include relevant AVC messages rather than disabling it.

References: [Rocky 10 release notes](https://docs.rockylinux.org/latest/releases/release_notes/10_0/), [Rocky Nginx and SELinux guidance](https://docs.rockylinux.org/guides/web/nginx-mainline/).
