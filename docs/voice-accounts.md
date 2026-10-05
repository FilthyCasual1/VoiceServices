# My Account and optional voice identities

The core My Account page includes editable display name, email, contact number,
time zone, password management, current/other active sessions, and signing out
other sessions. Optional addons supply linked-service panels; the core does not
contain CUCM provisioning code. Contact details are portal profile data, not an
automatic directory synchronization.

Install the **Voice Services** package for its phone-account panel and
**Administration > Phone account links**. Administrators can link existing portal
users to CUCM user IDs, or explicitly create a new local CUCM end user via AXL and
link it. Each remote identity can map to only one portal account. Standard users
can refresh only their own linked profile through My Account.

## AXL connection

1. Enable CUCM AXL SOAP Service and create a service account with permissions for
   `getUser` and, for provisioning, `addUser`. A read-only AXL role cannot create users.
2. In the Voice administration page, save `https://your-host:8443/axl/` and an
   optional trusted CA certificate file on the portal server. TLS verification is
   required. This adapter uses the 12.5 schema.
3. Supply `SERVICEREADY_AXL_USERNAME` and `SERVICEREADY_AXL_PASSWORD` to the portal
   service environment. On Alpine, put exported variables in
   `/etc/conf.d/serviceready`, owned by root with mode 0600, then restart the portal.
   Credentials are not stored in the portal database or served in forms.
4. Create the ServiceReady user in Users and passwords. In Phone account links,
   either map an existing CUCM ID or use Create CUCM account with a separate
   password and optional numeric PIN. Explicitly confirm creation.
5. Sign in as the linked user, open My Account, and refresh the linked profile.

Creation uses `addUser` with first/last name, user ID, separate password/PIN and
Standard CCM End Users membership. It does not assign devices, lines, voicemail,
self-provisioning templates, or LDAP synchronization. Those remain native system
configuration tasks. Passwords/PINs supplied for creation are not persisted.
Remote faults or timeouts are reported; a timed-out create may have succeeded,
so verify the CUCM user before retrying. Deleting a portal user does not delete
the CUCM user, and changing a portal password does not change the CUCM password.

Lookups display cached name, email, telephone, primary extension and associated
devices with a refresh time. These are read-only; they do not replace Alpine/local
authentication, CUCM authentication, extension mobility, or SSO. Removing Voice
removes the AXL UI and executable code while retaining saved mappings.

Tests verify request construction, identity isolation, explicit provisioning
confirmation, response handling, and secret omission from displayed/saved data.
No live CUCM instance has been supplied; real 12.5 schema compatibility, policy,
permissions and successful provisioning still need testbed verification.

References: [Cisco AXL guide](https://developer.cisco.com/docs/axl/axl-developer-guide/),
[Cisco addUser sample](https://developer.cisco.com/docs/axl/php-quickstart/),
[Cisco AXL password/PIN FAQ](https://developer.cisco.com/docs/axl/faq/).
