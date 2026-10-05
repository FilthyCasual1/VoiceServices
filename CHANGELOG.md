# Changelog

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
