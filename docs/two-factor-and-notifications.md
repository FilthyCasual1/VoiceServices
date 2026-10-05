# Two-factor authentication and notifications

In **My Account > Security**, confirm your current password and choose **Set up
authenticator**. Scan the locally generated QR code in Google Authenticator (or
another TOTP app), then enter its current six-digit code. A manual setup key is
also available. Setup expires after ten minutes and belongs to the initiating
session. Two-factor authentication starts only after code confirmation.

Save the ten recovery codes displayed after enrollment. Each works once and is
stored only as a hash. Existing other sessions are signed out when enabling or
disabling two-factor authentication. Disabling requires the current password and
a fresh authenticator code or unused recovery code.

Passwords alone no longer finish portal sign-in for enrolled accounts. Challenges
expire after five minutes, are single-use, and permit ten attempts. Verification
also limits failures per account, rejects used TOTP time steps, and allows one
30-second step of clock drift. Keep the host clock synchronized and use HTTPS in
an actual deployment. Enrollment secrets must be readable by the application;
protect the database and backups. This protects portal sign-in, not Alpine SSH or
Cisco/native application logins. There is no administrator bypass of enrolled MFA.

**Administration > Notifications** lets administrators deliver a subject and text
to one user or all existing accounts. The private My Account inbox shows sender,
time, unread counts and controls to mark one/all read or delete a message.
System/addon code can use `account.notify(app, user_id, title, body)` to deliver a
notice. Delivery is inside the portal; it does not send email or push notifications.

## Password and account recovery

The login page links to `/recover`. Users can request administrator review and
supply contact details without disclosing whether a username exists. Requests do
not authorize a reset. Administrators use **Administration > Account recovery**,
verify ownership outside the portal, confirm their current password, and issue a
single-use code valid for 30 minutes. Deliver that code securely to its verified
owner. The owner chooses a new password in the recovery form; sessions and phone
bindings are revoked. MFA remains enabled unless the administrator explicitly
approves lost-authenticator recovery. Alpine resets affect only enrolled non-system
accounts through the privileged broker. No email transport or automatic email reset
is currently configured.

## One-click host updates

**Administration > Overview > Portal and host updates** provides **Update OS**
and **Update INSAP** on Alpine installations. OS updating runs `apk update` and
`apk upgrade` without rebooting. INSAP updating uses a root-owned checkout of the
approved repository's main branch, backs up SQLite/configuration to
`/var/backups/serviceready`, installs dependencies, refreshes only installed addons,
and restarts portal workers. Status is exposed through the root broker; updates
run in a separate process with a lock. Failures do not perform automatic rollback.
Installations made before these controls need the installer run once to deploy the
worker and its trusted checkout. Archive-only installations must obtain a Git
checkout to use INSAP updating. Actual OS upgrades require validation in the Alpine
testbed; development previews intentionally disable these actions.
