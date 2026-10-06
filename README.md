# ServiceReady

Integrated Network Service Access Portal with an appliance-style interface,
account authentication, an administrator/user shell, and independently installed
addon files. The bare core installs no optional addons.

## Install on Rocky Linux 10

Clone main on a fresh Rocky 10 VM, then run as root:

```sh
bash install-rocky.sh
```

The menu-based installer configures the portal address, HTTPS firewall access and
optional addon packages. It installs systemd services, Nginx HTTPS and local
Rocky account authentication. See [Rocky deployment](docs/rocky-install.md).
The [Alpine installer](docs/alpine-install.md) remains available for existing deployments.

## Addons

Download `.sraddon` files from [packages/addons/1.26.1](packages/addons/1.26.1/) and
upload them through **Administration > Addons**. Available packages: Downloads,
Voice Services, Server Management, FTP Update Repository, PXE and Image Deployment,
and ESXi Management. Uninstall removes package files while retaining saved data.

[Package installation and ESXi management](docs/addon-packages.md) ·
[Core administration](docs/core-administration.md) ·
[Account and AXL setup](docs/voice-accounts.md) ·
[Bare installation](docs/bare-install.md) ·
[Alpine deployment and system accounts](docs/alpine-install.md) ·
[PXE and download setup](docs/downloads-and-pxe.md)

## Develop and build

```sh
python3 tools/build_addons.py
python3 -m pip install pyftpdlib==2.1.0
python3 -m unittest discover -s tests
python3 -m pip wheel --no-deps --wheel-dir dist/core .
cp config.bare.json config.json
python3 -m voiceservices create-user admin --admin
python3 -m voiceservices serve
```

Core builds exclude addon implementations; addons are built separately. GitHub
Actions uploads both as build artifacts. Packages are checked against the core's
compatibility/checksum catalog; arbitrary third-party Python is not accepted.
The application requires Python 3.10+. Production deployment uses Waitress and
HTTPS with secure cookies. The built-in server is for local development.

ESXi management includes inventory and VM power requests; no live ESXi host has
been tested yet. PXE/disk restoration requires testbed validation. Voice services
retain the existing development bindings and phone XML applications; native
telephony provisioning, CTI and recording adapters remain incomplete.

[SMTP notification receiver setup](docs/smtp-notifications.md).

[Login rate limiting and optional Fail2ban setup](docs/login-protection.md).

[Scheduled portal and OS updates](docs/update-schedules.md).

Host maintenance, terminal, network/NTP settings and upload disk setup are part of the core. See [host configuration](docs/host-configuration.md). To upgrade an existing Rocky installation to this release, pull main and rerun `sudo bash install-rocky.sh` so the new root host worker and OS dependencies are installed. Settings and accounts are retained.

Later releases can be installed from Administration → System → Portal and host updates → Update INSAP. The connected host updater preserves configuration and accounts and refreshes installed official addons.

If an older GUI update leaves the portal returning 502 with `No module named voiceservices.server`, run `git pull` followed by `sudo bash repair-rocky.sh` in this checkout. The repair restores service-group access to the root-owned runtime, verifies imports under the service account, and restarts the portal without resetting configuration, users or uploads. Future updates repeat this verification before restarting.

Root console recovery: `sudo serviceready-admin-reset <administrator>` prompts for a new password, optional two-factor reset and confirmation, then revokes that administrator’s portal sessions. It works without the web server or portal Python environment. Enrolled Linux-backed administrators have their OS password updated too.

### Invited registration and IPv6

Create a single-use invitation in Administration → Users and Accounts → Account invitations. Give the code to the new user, who enters it during account onboarding. Codes can expire after 1, 7 or 30 days and can be revoked before use. Registration must also be enabled in Security. Existing accounts and administrator-created accounts continue to work.

Network and time supports IPv4 and IPv6 independently. Keep existing settings when changing only the other protocol; IPv6 supports automatic addressing, DHCPv6, static addresses and disabling. Network changes must still be confirmed within 90 seconds or the original profile is restored. The managed HTTPS proxy listens on both protocols and refreshes certificate addresses from current host interfaces.

Install official addons from Administration → Addons → Install from repository, or upload a compatible `.sraddon` file using Manual installation. Repository installation downloads the package version approved by the installed core; it does not execute newer unapproved addon code.
