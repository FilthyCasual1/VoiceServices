# Host maintenance and browser terminal

Host maintenance and Host terminal are now built into the core; no addon installation is needed. Both require the Linux account broker. See [Host configuration](host-configuration.md) for disk, network and NTP setup.

Host maintenance shares the existing update worker and lock. Each task requires administrator access, CSRF validation, password confirmation and an explicit checkbox:

- Clean unused Linux package cache with `apk cache clean (Alpine) or dnf clean packages (Rocky)`. Installed packages remain installed.
- Remove regular portal temporary files older than seven days from `/var/lib/serviceready/tmp`. Directories and symlinks are not removed.
- Trim regular `*.log` files in `/var/log/serviceready` to their latest 1 MiB. Older log history is deleted; retain/export logs separately if needed. Concurrent writes may be affected during trimming.

The UI displays the worker's status and completion message. No arbitrary command, path, package-removal, reboot or service-stop operation is accepted by the cleanup interface.

Host terminal uses self-hosted xterm.js 6.0.0 (MIT; license shipped in static/xterm-LICENSE.txt) with a real PTY. The terminal opens only after a local portal administrator confirms their Linux password. The broker drops supplementary groups/UID/GID to the enrolled OS account before starting `/bin/sh -l`. It overrides the account's usual nologin shell only for this explicitly authenticated terminal. Existing OS permissions apply; it is not a root shell. Elevation requires host-managed doas/sudo policy and credentials; the portal does not configure or grant it. An absent home directory uses `/` as the starting directory.

Terminal capabilities are bound to the administrator username and portal session token. Every request requires a valid admin session and CSRF token. At most four terminals run at once. Sessions expire after 60 seconds without browser heartbeat or 30 minutes total, and foreground shell groups are terminated on close. Leaving the terminal page closes its session; abrupt disconnects expire on the broker. Browser commands are not stored in portal audit records; opening/closing and cleanup requests are audited. Shell history and command effects follow OS behavior, and detached jobs may outlive their terminal.

Opening the terminal uses normal full-page navigation because its page alone allows the inline styles needed by the terminal renderer. Scripts remain restricted to self-hosted assets. Other portal pages retain the stricter style policy. Terminal data travels through bounded, CSRF-protected same-origin requests; HTTPS is required for deployments outside the loopback development preview.

The Linux installer already copies the updated account broker and maintenance worker. Existing deployed installations must run the installer/update to receive these host components as well as installing the addon. The local development preview has no connected Linux broker. An actual unprivileged local PTY, session isolation and cleanup behavior were tested; real root-broker UID switching and Linux maintenance still require testbed validation.

Rocky Linux 10 uses systemd and DNF; see [Rocky installation](rocky-install.md). Host-account switching on each distro still requires live VM validation.
