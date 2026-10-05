# ServiceReady platform modules and accounts

## Core

Authentication, registration, sessions, My Account/password changes, the user
navigation shell, and Administration/Addons form the permanent core. Guest
navigation remains Home and Downloads, with registration and sign-in entry
points. Installation state persists in SQLite; removing optional modules cannot
remove the authentication or management shell.

## Optional modules

Administration > Addons installs/removes trusted bundled capabilities:

- Voice Services: My Phone, contacts, phone XML routes, phone application plugins,
  recordings placeholders and voice-client download listings.
- Server Management: external application links and service/provisioning settings.
- FTP Update Repository: streaming browser uploads, checksums, and a read-only FTP
  server. Independent of the other two modules.

Voice Services and Server Management start installed to preserve the existing
interface. Removal disables routes and hides navigation. Saved contacts/settings
and uploaded packages remain for reinstall. Core uploads require administrator
access plus a valid form token. The file repository addon starts disabled until
an FTP credential is configured and it is enabled. Removal stops its listening
server automatically through the installed worker; it does not delete files or
uninstall the shared Python runtime/dependencies.

Module implementations are trusted code shipped with ServiceReady. This is a
lifecycle registry, not permission to execute arbitrary uploaded Python packages.
Phone text plugins remain declarative packages. New module code should declare
its owned routes/navigation, register its install state, and keep module-specific
controls and data outside core account handling. The current catalog lives in
`voiceservices/modules.py`; more module renderers can be added there and wired
into the portal. Backend adapters are still incomplete and are not implied by an
installed module.

## Passwords and Alpine accounts

My Account (also the header's Change password link) requires your current
password and changes it, revoking existing portal sessions and phone bindings.
The next login uses the new password. Local preview accounts continue to use
SQLite hashes. Fresh Alpine installations use `auth_backend: alpine` and the
root-owned local broker socket instead: password authentication and changes use
Alpine's shadow account database. The portal retains profile/role data, not a
copy of the system password hash. Successful login automatically creates a
standard-user portal profile for an enrolled system account.

Only non-system users (UID >= 1000) enrolled in `serviceready-users` may sign in;
root and other system identities are excluded. To enroll an existing Alpine
account as root:

```sh
addgroup USERNAME serviceready-users
```

Portal registration creates an Alpine account with a `nologin` shell, preventing
self-registration from granting shell access. A host administrator may separately
assign a login shell. Password changes through Alpine itself also affect future
portal logins. Portal administrator status is stored separately and never inferred
from root/wheel membership. New registrations are always standard users.

Existing installations keep their existing auth configuration on installer rerun.
To move an existing local-auth deployment to Alpine authentication, create or
enroll matching Alpine usernames, set their system passwords, then set
`auth_backend` to `alpine` in `/etc/serviceready/config.json` and restart
ServiceReady. Existing portal roles/preferences stay associated with matching
usernames. Old portal password hashes cannot be migrated into known passwords.
No root password is requested by the web server. The account broker accepts only
root and the service UID via a Unix socket, and validates target account group
membership. This Alpine broker has not been exercised on a live Alpine host yet.

## FTP upgrade workflow

1. Install FTP Update Repository in Administration > Addons.
2. Open Update files. Set a dedicated FTP username/password, control port 21,
   passive data ports (default 30000–30009), and optionally an advertised address.
3. Enable the addon and allow its ports only on the testbed network.
4. Upload the ISO/COP/update file through the browser. File size is capped at
   8 GiB by default; filenames cannot include paths and existing files are never
   overwritten. Completed files show their SHA-256 checksums. Temporary uploads
   are outside the FTP root.
5. In the application's native upgrade screen, choose Remote Filesystem, FTP,
   the ServiceReady VM address, directory `/`, and the FTP credentials.
6. The target retrieves the update; start installation and any required reboot
   in that application's native workflow. ServiceReady does not push files into
   a target filesystem or trigger upgrades/reboots.

The addon worker initially binds the standard FTP port as root, then drops to
`serviceready` before accepting clients. Configuration changes restart the worker
through OpenRC. No anonymous access or FTP write/delete rights are granted.
FTP is plaintext; this is an isolated-testbed feature. SFTP is not yet provided.
Large web requests are spooled by Waitress into temporary storage before the
WSGI upload handler streams them into the repository: provide enough disk space
for both a request spool and its repository copy. Configure TMPDIR on a disk
filesystem rather than a small RAM-backed /tmp for multi-gigabyte updates.

Cisco documents the pull workflow in its [CUCM upgrade tasks](https://www.cisco.com/c/en/us/td/docs/voice_ip_comm/cucm/upgrade/12_5_1/cucm_b_upgrade-migration-guide-1251su7/cucm_b_upgrade-guide-1251su2_chapter_01100.html)
and [Unity Connection software upgrade guide](https://www.cisco.com/c/en/us/td/docs/voice_ip_comm/connection/12x/os_administration/b_12xcucosagx/b_12xcucosagx_chapter_0110.html).
