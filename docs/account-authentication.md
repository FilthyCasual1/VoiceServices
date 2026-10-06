# Account authentication

Administrator → Account authentication configures LDAP, Kerberos and RADIUS. All providers start disabled. Saving a provider requires the current local administrator password and revokes that provider's existing sessions. Enabling requires an HTTPS public portal URL, installed client dependency and an explicit username allowlist.

Local accounts retain their existing backend. On Alpine, local administrators authenticate through the root-owned Alpine account broker; external providers do not replace this path. External logins create ordinary user profiles only, named `ldap:username`, `radius:username` or `kerberos:user@REALM`. These identities cannot become local administrators or collide with a local administrator sharing the same upstream username. Remove an external user through Users and Accounts to disable portal access without changing the upstream account; the disabled identity is retained to prevent automatic recreation. There is no directory synchronization or automatic group-to-role mapping.

## LDAP

Configure a hostname, LDAPS port (default 636) and bind template containing one `{username}`, such as `uid={username},ou=People,dc=example,dc=org` or `{username}@example.org`. Only certificate-verified LDAPS is supported. Use the system trust store or provide a readable PEM CA file. User passwords are used only for the bind and are not stored. Search-bind, StartTLS and arbitrary unencrypted LDAP are not implemented.

## Kerberos

Configure the realm, HTTP service principal (`HTTP/portal.example.org@EXAMPLE.ORG`) and service keytab path. The keytab must be readable by the portal service account and protected from other users. Configure the host's `/etc/krb5.conf`, KDC discovery, DNS and clock synchronization separately. Permit full principal names in the allowlist (`alice@EXAMPLE.ORG`) for consistent password and browser identity mapping. Password sign-in validates a service ticket using the configured keytab rather than trusting only a successful ticket acquisition. Credentials remain in process memory.

Browser SSO uses the Kerberos link on the login page and HTTP Negotiate. The browser must trust the portal hostname for integrated authentication; the reverse proxy must preserve Authorization and WWW-Authenticate headers. NTLM and forwarded remote-user headers are not accepted. Short-lived negotiation contexts are bound to the client address and protected by secure cookies. Existing portal authenticator enrollment still requires the second factor after either password or browser authentication.

The Python gssapi library requires native Kerberos libraries/development headers to install. The Alpine installer installs krb5, krb5-dev, python3-dev and build-base and installs the project's identity dependencies. This development machine lacks krb5-config; Kerberos paths have mocked integration tests but have not been tested against a live realm or browser domain login. Validate both methods in the testbed before deployment.

## RADIUS

Configure the server, authentication port (default 1812), shared secret and permitted usernames. This release uses PAP Access-Request with Message-Authenticator and requires a verified response authenticator plus a valid Message-Authenticator on Access-Accept. Configure the server accordingly. Access-Reject, Access-Challenge, timeouts, malformed responses and missing/invalid authenticators fail closed. Challenge-response, EAP and RadSec are not implemented. PAP over UDP is not a substitute for transport encryption; isolate the management network.

## Account security

Password rate limiting, portal MFA and session policy remain active for external sign-ins. Password changes and password recovery for external identities belong to their identity provider. Current-password confirmations for authenticator enrollment use the external provider. Provider failures do not fall back to a local account. Removing an allowlist entry or disabling a provider invalidates its external access; provider saves revoke sessions. This portal does not persist external passwords or Kerberos tickets. RADIUS shared secrets are stored in the protected portal database and never echoed by the form. No production directories or KDCs have been contacted during development.

On other supported Linux hosts, install the identity extra alongside native Kerberos development tools:

```sh
pip install '.[identity]'
```
