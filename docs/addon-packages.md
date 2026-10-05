# File-based addons (1.3.0)

The installed core contains accounts, authentication, the portal shell, artifact
transport, and the addon installer/supervisors. Voice screens and XML services,
download catalog UI, service settings, FTP/PXE workers, and ESXi management are
separate code packages. Their implementations are absent from the core wheel.

Upload a `.sraddon` file in **Administration > Addons**. Uninstall removes the
installed package directory and its listing, hides its links, and blocks its routes.
The Addons page lists only uploaded packages; reinstalling requires the package file. Existing
application data and uploads remain for reinstallation. There are no enable-only
installation buttons. Workers stop serving when their package is removed.

Official packages are in `packages/addons/1.3.0/` in the repository:

- `downloads-1.3.0.sraddon`
- `voice-1.3.0.sraddon`
- `server-management-1.3.0.sraddon`
- `ftp-updates-1.3.0.sraddon`
- `pxe-1.3.0.sraddon`
- `esxi-1.3.0.sraddon`

Packages contain executable code. The installer accepts only packages whose ID,
version, API and payload SHA-256 match the catalog shipped with this core release.
It rejects modified packages, unknown versions, duplicate files and traversal
paths. It does not fetch arbitrary third-party Python or run uploaded installer
scripts. This first package ABI has no dependency resolver or automatic upgrade.
Uninstall before replacement. After a core update, install matching packages;
older incompatible packages are unavailable, and their saved data remains.

From the repository, build packages using `python3 tools/build_addons.py` and
build the core with `python3 -m pip wheel --no-deps --wheel-dir dist/core .`.
Changing addon source requires rebuilding the core catalog too. GitHub Actions
builds and publishes downloadable build artifacts on repository pushes.

CLI installation is also available:

```sh
python3 -m voiceservices --config config.json install-addon packages/addons/1.3.0/downloads-1.3.0.sraddon
python3 -m voiceservices --config config.json uninstall-addon downloads
```

Use the installed virtual-environment interpreter and `/etc/serviceready/config.json`
on Alpine. Default package storage is `<database-path>.addons`, or configure
`addon_directory`. Alpine installations use `/var/lib/serviceready/addons`.
The Alpine installer installs the core and idle supervisors; it installs no addons.
Rerun it to update the core. Preserve configuration, databases and upload directories.

## ESXi management

Install the ESXi package, then configure an HTTPS host address and username in
Administration > ESXi management. Certificate verification is on by default;
allowing an untrusted certificate is an explicit lab setting. The portal stores
connection defaults but never saves the ESXi password. Supply it with each request.

The administrator-only ESXi page retrieves host, datastore and VM inventory through
the vSphere SOAP API. It provides VM power-on, suspend, power-off and guest shutdown
requests. VM actions require an explicit confirmation selection; guest shutdown
requires VMware Tools. Submitted tasks are shown as accepted, not completed;
refresh inventory to verify. ESXi account permissions and licensing must allow
API access. There is no remote console, patching, datastore upload, VM creation or
host lifecycle workflow in this release.

The ESXi adapter is tested using mocked responses and request validation. No live
ESXi host has been supplied, so real inventory and power operation compatibility
remain unverified. PXE and disk restoration also need actual testbed validation.

API references: [vSphere SessionManager](https://developer.broadcom.com/xapis/vsphere-web-services-api/latest/vim.SessionManager.html),
[VirtualMachine controls](https://developer.broadcom.com/xapis/vsphere-web-services-api/latest/vim.VirtualMachine.html).
