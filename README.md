# ServiceReady

An intentionally plain, circa-2006 modular Integrated Network Service Access Portal for x86 / VMware ESXi. The permanent core is authentication and the admin/user shell. Voice Services, Server Management, and the FTP Update Repository are independently installable/removable optional modules.

The portal guides setup of storage, voice, email, domain and other network services through optional capabilities. The homepage and account flow are service-neutral; voice setup guidance belongs to the Voice Services module. Storage, email and domain integrations are not implemented by the descriptive homepage categories.

## Current capabilities

- Server-rendered portal with blue header, compact top navigation, small text, tables, and conventional forms; no JavaScript dependency.
- Local accounts with PBKDF2 password hashing, expiring sessions, CSRF protection, and administrator/user roles. Native admin links require portal login; the destination also authenticates access.
- Persistent personal and shared contacts, search, and administrator-only shared-directory writes.
- Phone-only decimal calculator through Cisco XML services.
- Per-user app preferences, independent of physical phones.
- Temporary application terminal bindings: moving to another phone revokes the previous token; explicit application sign-out revokes access.
- XML Services launcher, directory (first 32 matching contacts), calculator input and result screens.
- Configurable native CUCM, CUC, IM&P, Self Care, and OpenWrt links.
- Download listings for operator-supplied Jabber and IP Communicator installers; installers are not included. URLs can point to a separately hosted local file server.

## Run locally

Python 3.10+; no runtime dependencies are required when running from the checkout.

```sh
cp config.example.json config.json
python3 -m voiceservices create-user administrator --admin
python3 -m voiceservices serve
```

Open `http://127.0.0.1:8080`. Only Home and Downloads are available to guests. Sign in to access the other portal pages. The homepage links to working standard-user registration and phone setup. Registration creates a hashed-password account and signs the user in; administrator access is granted only through the local administrator command. Create additional users with `python3 -m voiceservices create-user USERNAME`. Passwords are entered interactively, never supplied on the command line. There are no default accounts or passwords.

The example configuration disables Secure cookies **for localhost development only**. Deployment requires HTTPS, `secure_cookies: true`, and a correct externally reachable `public_url`. Put a production WSGI server and TLS reverse proxy in front of the application; the bundled server is for development. Do not expose the development server to the Internet. Configure access-log redaction for `/phone/` URLs because development bindings carry bearer tokens.

## Phone development

Sign in to the portal, open **My Phone**, and bind a `SEP` device name. Configure the generated private URL as that test phone's Services URL. The binding expires after eight hours. Device names are format-checked, **not verified against CUCM**. This is an explicit development mechanism, not native Extension Mobility or an authorization proof from a phone MAC address.

Phone endpoints are read-only GET XML services. Directory entries are escaped and dialable. Exact XML object compatibility, character encoding, screen layout, and active-call behavior must be tested on physical 79xx handsets. No handset or Cisco appliance was available during this build.

## Not connected yet

The interface labels these integrations as unavailable rather than inventing data:

- CUCM AXL provisioning, JTAPI call context, and native Extension Mobility synchronization.
- Automatic capture of the currently dialed number and portable call history.
- Unity Connection CUPI/CUMI and playback integration.
- IM&P provisioning and health monitoring.
- RSS, weather, and flight providers.
- SNMP/OpenWrt WAN control and authenticated status-widget pushes.
- Call recording, media capture, browser audio playback, and handset playback.
- File upload/installer hosting within this process.

See [architecture and integration roadmap](docs/architecture.md). Native application links open their own login pages; portal login is not SSO. Native applications continue enforcing their own permissions.

## Verify

```sh
python3 -m unittest discover -s tests -v
```

Tests exercise contact isolation, server-side roles, session and binding expiry, CSRF, XML escaping, link safety, calculator parsing, and roaming token invalidation. CI runs the suite on Python 3.10 and 3.12.

## Native CUCM self-provisioning

**Set Up Phone** supplies TFTP/network details, the self-provisioning IVR number, and instructions for CUCM auto-registration and its universal templates. It creates no local registration queue or device object. Configure `self_provisioning.ivr_number`, `network`, and explicit `users` mappings in the private config. A mapping is keyed by local portal username and contains `user_id`, `self_service_id`, and `extension`. Only that signed-in user sees their own mapping. These are operator-provided details, not live CUCM reads. Never add PINs or passwords to this section.

CUCM must separately enable auto-registration and self-provisioning, assign universal device/line templates and eligible user profiles, and configure the native IVR or supported phone screen. Native URL workflow support requires testing on the selected 79xx models. Self-provisioning and Extension Mobility are distinct operations.

### Phone plugins
Applications is an installed-plugin manager. Administrators paste a separate JSON
package to install it, edit its configuration, disable it, or remove it. Browsing
requires login; changes require administrator access and a form token. Enabled
packages appear in the telephone Services menu. No utilities run in the portal.

Try `plugins/site-information/plugin.json`. Uploaded packages currently support
`kind: text`, with up to twelve named `fields` and `{field}` substitutions in
`text`. Screens are XML escaped. Packages persist in SQLite and cannot execute
Python or fetch arbitrary URLs. Calculator ships as a trusted renderer. Dynamic
RSS, weather, flight, and network integrations need additional trusted provider
renderers; installing a text manifest does not implement those providers.

### Versions

The footer and package metadata share `voiceservices/version.py` as their version
source. Every subsequent change increments the release version and gets a short
entry in `CHANGELOG.md`. Use `python3 tools/bump_version.py patch "Description"`
for fixes and small edits; use `minor` for new features and `major` for breaking
changes. The current release is shown in the footer and CHANGELOG.md.

### Alpine testbed installation

See [Alpine / ESXi installation](docs/alpine-install.md). Clone the current
`initial-portal` branch on an Alpine VM and run `sh install-alpine.sh` as root.
The installer preserves configuration and accounts on updates and installs an
OpenRC-managed service using Waitress.

### Modular core and administration

The admin/user shell and authentication form the core. Voice Services, Server
Management and FTP Update Repository are optional modules controlled from
Administration > Addons. Removal hides their UI and disables their routes while
retaining data for reinstall. See [Modules and Alpine accounts](docs/modules-and-accounts.md)
for system password integration, password changes, web uploads and FTP delivery.

Internal tools, downloadable packages, and optional PXE ISO/image restoration are described in [Downloads and PXE](docs/downloads-and-pxe.md).
