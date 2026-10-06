# Changelog

## 1.18.0 — 2026-10-06

Add scheduled and one-click VM guest-tool updates: repository-managed VMware/VirtualBox tools and checksum-verified Oracle Guest Additions matching the VirtualBox host.

## 1.17.6 — 2026-10-06

Combine updates and schedules into Host maintenance; remove repeated password entry for confirmed log, temporary-file and package-cache cleanup.

## 1.17.5 — 2026-10-06

Embed the authenticated host terminal in Host maintenance and remove its separate navigation entry; retain compatibility with existing terminal links.

## 1.17.4 — 2026-10-06

Combine automatic update schedules with Portal and host updates, keeping separate save and update actions and removing the standalone navigation entry.

## 1.17.3 — 2026-10-06

Place distro and INSAP versions beneath the update page logo, remove duplicate heading/version line, and align update buttons in one row.

## 1.17.2 — 2026-10-06

Align Overview section headings and tables; move distro branding, version and compact refresh control into a single toolbar.

## 1.17.1 — 2026-10-06

Keep distro branding and installed INSAP version on Overview; restrict all update controls and submissions to Portal and host updates.

## 1.17.0 — 2026-10-06

Add confirmed local-administrator VM shutdown and restart controls to Host maintenance, using delayed host power operations.

## 1.16.17 — 2026-10-06

Exclude boot and system disks, including their partition and logical-volume trees, from upload storage discovery and selection.

## 1.16.16 — 2026-10-06

Keep expected connection failures quiet while the recovery script waits for portal startup; retain service diagnostics when recovery fails.

## 1.16.15 — 2026-10-06

Preserve service-account ownership when GUI updates refresh addons and recover the portal if refresh fails.

## 1.16.14 — 2026-10-06

Add root-only Linux console administrator recovery with optional two-factor reset and session revocation.

## 1.16.13 — 2026-10-06

Repair GUI update runtime permissions and verify imports as the service account before restarting; include Rocky recovery script.

## 1.16.12 — 2026-10-06

Serve styled Nginx outage and request error pages with safe automatic recovery during portal restarts.

## 1.16.11 — 2026-10-06

Automatically poll update progress, reconnect after restart, and remove the manual status refresh control.

## 1.16.10 — 2026-10-06

Keep storage and network/time pages usable when host tooling is unavailable, with independent diagnostics and GUI-upgrade helper recovery.

## 1.16.9 — 2026-10-06

Place footer copyright at the far right while retaining branding and version on the left.

## 1.16.8 — 2026-10-06

Separate update status from the distro logo to prevent overview collisions.

## 1.16.7 — 2026-10-06

Expose the connected INSAP updater on a dedicated System GUI page with installed-version and restart guidance.

## 1.16.6 — 2026-10-06

Align header account actions beneath the profile picture, with logout at the far right.

## 1.16.5 — 2026-10-06

Graceful missing upload-volume status and portal setup of a blank replacement disk.

## 1.16.4 — 2026-10-06

Keep inbox activity in the header action row without covering account identity on narrow displays.

## 1.16.3 — 2026-10-06

Profile location, address and multiple phone contact fields.

## 1.16.2 — 2026-10-06

Offline Rocky distro logo with Powered by caption.

## 1.16.1 — 2026-10-06

Footer copyright notice.

## 1.16.0 — 2026-10-06

Core host maintenance and terminal, Rocky network/NTP controls, and dedicated upload disk configuration.

## 1.15.1 — 2026-10-06

Show installer stage progress, elapsed time, current activity and live log output in a gauge, with console progress fallback.

## 1.15.0 — 2026-10-06

Add menuconfig-style Rocky Linux 10 deployment with address/firewall/addon choices, systemd, OS-account authentication, Nginx HTTPS, local CA, DHCP address tracking and DNF maintenance.

## 1.14.4 — 2026-10-06

Add one-command repair for stale Alpine HTTPS addresses, with backups and automatic DHCP/static address following.

## 1.14.3 — 2026-10-06

Repair Alpine installer repository preflight, staged logging, resumable setup and verified HTTPS startup.

## 1.14.2 — 2026-10-06

Default blank installer URL to current host addresses; follow DHCP/static changes in portal URLs and managed local HTTPS without restarting the portal.

## 1.14.1 — 2026-10-06

Prepare Alpine VM deployment: main-branch installation instructions, bare defaults and optional local HTTPS proxy for host tools.

## 1.14.0 — 2026-10-06

Add installable host cleanup tools and a session-bound browser PTY terminal running as the local Alpine administrator OS account.

## 1.13.3 — 2026-10-06

Show host domain/hostname in the account header when the host has a configured domain.

## 1.13.2 — 2026-10-06

Rename the System Operator administration tree to System.

## 1.13.1 — 2026-10-06

Add a remembered overview auto-refresh switch.

## 1.13.0 — 2026-10-06

Add explicit LDAP, Kerberos password/browser SSO and RADIUS authentication with local Alpine administrator access preserved.

## 1.12.2 — 2026-10-06

Add timezone dropdowns, rename Appearance and restore friendly usable default home and account guidance while preserving custom copy.

## 1.12.1 — 2026-10-05

Use direct setup-before-production guidance in default home blocks and account subtitles, preserving custom wording.

## 1.12.0 — 2026-10-05

Separate guest and signed-in home blocks with independent editing and automatic session-based selection.

## 1.11.0 — 2026-10-05

Add separately installable SNMPv2c monitoring, trap/inform reception, portal configuration and Alpine worker service.

## 1.10.3 — 2026-10-05

Accept addon packages across portal release versions when their API and approved code checksum match; explain incompatible API and code failures.

## 1.10.2 — 2026-10-05

Format portal and host uptime as days, hours, minutes and seconds; show rounded RAM and storage capacities in MB, GB or TB.

## 1.10.1 — 2026-10-05

Show available host OEM manufacturer, model, serial, board and BIOS identity on Overview.

## 1.10.0 — 2026-10-05

Preserve the masthead during content navigation, cache image responses with ETags, and refresh overview statistics in place every five seconds.

## 1.9.1 — 2026-10-05

Show the current date and time on the administration overview using global regional settings.

## 1.9.0 — 2026-10-05

Add portal-wide timezone and date/time format controls; use them for greetings, inbox and session timestamps and inherited update schedules.

## 1.8.2 — 2026-10-05

Combine user management, passwords and account recovery under Users and Accounts.

## 1.8.1 — 2026-10-05

Condense Look and Feel and home block editors into grouped collapsible controls and compact field grids.

## 1.8.0 — 2026-10-05

Add configurable timezone-aware daily and weekly automatic portal and OS update schedules with persistent run tracking.

## 1.7.0 — 2026-10-05

Add a core Security administration page for login limits, automatic source blocks, session policy and account registration.

## 1.6.0 — 2026-10-05

Add persistent atomic password and MFA login rate limiting with Retry-After responses and Fail2ban-compatible authentication events.

## 1.5.1 — 2026-10-05

Improve the inbox indicator with high-contrast text, stronger priority colors and a larger label.

## 1.5.0 — 2026-10-05

Add a separately installable receive-only SMTP notification gateway with inbox recipient routing and trusted-source restrictions.

## 1.4.1 — 2026-10-05

Compact the overview into side-by-side portal and host tables with tighter spacing and update controls.

## 1.4.0 — 2026-10-05

Add Info, Caution and Urgent notification priorities and a user-scoped unread indicator in the account panel.

## 1.3.7 — 2026-10-05

Remove the duplicate My Account main navigation tab; retain the profile-panel button.

## 1.3.6 — 2026-10-05

Split administration navigation into Administrator and System Operator trees with a shared overview.

## 1.3.5 — 2026-10-05

Use OS-neutral overview and host update labels while showing the detected OS and connected update provider.

## 1.3.4 — 2026-10-05

Add an optional custom login disclaimer controlled through Look and Feel.

## 1.3.3 — 2026-10-05

Show recommended image dimensions and display sizes in Look and Feel upload controls.

## 1.3.2 — 2026-10-05

Rename Branding to Look and Feel and customize logout confirmation and session-ended box text.

## 1.3.1 — 2026-10-05

Keep sign-in and account form tokens stable across tabs and return a usable sign-in form when the token expires.

## 1.3.0 — 2026-10-05

Custom sign-in/create-account box text and time-based greetings, optional 30-day sign-in, and square guest sign-in action.

## 1.2.8 — 2026-10-05

Confirm session termination in a centered appliance-style panel, with styled actions and a logged-out page that redirects to sign-in.

## 1.2.7 — 2026-10-05

Align styled My Account and Inbox header actions with logout and emphasize logout in red.

## 1.2.6 — 2026-10-05

Place logout below the header profile picture and move guest sign-in away from the system row.

## 1.2.5 — 2026-10-05

Right-align the sign-in and create-account action buttons to finish the portal shell.

## 1.2.4 — 2026-10-05

Style account creation with the same centered appliance panel and banner as sign-in.

## 1.2.3 — 2026-10-05

Detect the host distribution and fetch its logo with a sanitized local cache and offline fallback.

## 1.2.2 — 2026-10-05

Separate My Account profile, inbox and security pages.

## 1.2.1 — 2026-10-05

Add the supplied Alpine Linux logo to the host-update overview panel.

## 1.2.0 — 2026-10-05

Authenticator two-factor login with local QR enrollment, replay protection and single-use recovery codes; administrator notification delivery and inbox read controls; Secondary masthead naming; administrator-reviewed password/account recovery and a styled centered sign-in panel; one-click Alpine OS and INSAP updates with status and backups; expanded OS, kernel, CPU and runtime overview.

## 1.1.2 — 2026-10-05

Organize My Account into a combined profile panel, notification inbox and aligned security/session sections.

## 1.1.1 — 2026-10-05

Align masthead account details beside the avatar with tighter, consistent label spacing.

## 1.1.0 — 2026-10-05

Secondary header image, profile picture uploads, and a private notification inbox with read and delete actions.

## 1.0.7 — 2026-10-05

Place the wide masthead white divider at the actual photo edge, including when the photo ends before the account panel.

## 1.0.6 — 2026-10-05

Styled login and navigation errors with clear recovery links in the portal shell.

## 1.0.5 — 2026-10-05

Keep a thin white divider at the right edge of the wide masthead image.

## 1.0.4 — 2026-10-05

Selectable wide and compact mastheads; wide stays left aligned and visible, compact retains responsive hiding.

## 1.0.3 — 2026-10-05

Full-width brand-side masthead, administrator image replacement, and home-block page link legend.

## 1.0.2 — 2026-10-05

Administration overview lists only installed addons and shows an empty state when none are installed.

## 1.0.1 — 2026-10-05

Show only uploaded addon packages in Administration; uninstall removes the addon listing.

## 1.0.0 — 2026-10-05

CrystalBlue: CasualNetworks branding, custom-brand attribution, and a legend for home-page block controls.

## 0.10.0 — 2026-10-05

Add administrator AXL configuration and CUCM end-user creation with explicit identity linking.

## 0.9.0 — 2026-10-05

Expand My Account with profiles, security and session controls; add optional CUCM linked identity and read-only AXL lookup.

## 0.8.1 — 2026-10-05

Show host hostname and friendly named user greeting; retain administrator username and access display.

## 0.8.0 — 2026-10-05

Add portal-wide status overview and administrator user creation, role management, and deletion, including enrolled Alpine accounts.

## 0.7.0 — 2026-10-05

Add core branding controls, logo uploads, and administrator-editable homepage blocks.

## 0.6.0 — 2026-10-05

Separate optional modules into verified installable addon files; add standalone ESXi management package.

## 0.5.1 — 2026-10-05

Add bare installation profile with no optional modules enabled; preserve addon changes across restarts.

## 0.5.0 — 2026-10-05

Add independent internal Downloads module and optional PXE ISO/Clonezilla restoration addon with artifact hosting and proxy-DHCP/TFTP worker.

## 0.4.1 — 2026-10-05

Make core homepage, registration and administration guidance service-neutral and focused on setup of storage, voice, email and domain services.

## 0.4.0 — 2026-10-05

Make the admin/user shell and authentication the permanent core. Add removable Voice Services and Server Management modules, administration submenus, password changes, an Alpine account broker, and an optional read-only FTP update repository with web uploads. Revise the portal subtitle and masthead border.

## 0.3.0 — 2026-10-05

Add Alpine installer, supervised OpenRC service, and installed Waitress server.

## 0.2.2 — 2026-10-05

Use form-bound login tokens for proxied previews instead of comparing browser origins.

## 0.2.1 — 2026-10-05

Center account forms and rename the portal subtitle to Integrated Services Portal.

## 0.2.0 — 2026-10-05

ServiceReady portal with account registration, user sessions, phone plugins,
phone setup guidance, and the revised appliance interface. The footer and Python
package now use one release version. External service adapters remain pending.

## 0.1.0

Initial portal and phone XML service foundation.
