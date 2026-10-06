# ServiceReady

Integrated Network Service Access Portal with an appliance-style interface,
account authentication, an administrator/user shell, and independently installed
addon files. The bare core installs no optional addons.

## Install on Alpine

Clone this repository's `main` branch on a fresh Alpine/OpenRC VM, then run:

```sh
./install-alpine.sh --bare
```

The installer asks for a portal address and administrator credentials, installs
an OpenRC service, and connects authentication to enrolled Alpine accounts.
Rerun without `--bare` to update an existing installation.

## Addons

Download `.sraddon` files from [packages/addons/1.13.3](packages/addons/1.13.3/) and
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
