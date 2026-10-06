# Login protection

Administration → System → Security controls password and MFA budgets, time windows, automatic IP blocking, block duration, standard session duration, persistent sign-in and self-registration. Automatic blocks can be cleared there. These are portal-level controls; the optional Fail2ban firewall service remains host-managed.

By default, core password sign-in and two-factor verification each allow 10 POST submissions per source IP in a five-minute window. This includes successful, failed and expired-form submissions. Atomic SQLite reservations are shared across threads/processes and survive portal restarts. Expired buckets are pruned automatically. A throttled request receives a styled HTTP 429 response and Retry-After in seconds. Existing authenticated sessions are unaffected.

Failed password and MFA submissions emit timestamped `serviceready-auth login_failed ip=...` or `mfa_failed ip=...` events to standard error. Passwords, usernames, tokens and forwarded headers are not logged. On Alpine these go to `/var/log/serviceready/error.log`.

Optional Fail2ban deployment:

1. Install Fail2ban using your host package manager.
2. Copy `deploy/fail2ban/serviceready.conf` to `/etc/fail2ban/filter.d/serviceready.conf` and `deploy/fail2ban/serviceready.local` to `/etc/fail2ban/jail.d/serviceready.local`.
3. Adjust logpath, listening ports and the firewall action for your deployment. Set enabled=true, then reload Fail2ban. The sample bans after five failures in five minutes for 15 minutes.
4. Validate with `fail2ban-regex /var/log/serviceready/error.log /etc/fail2ban/filter.d/serviceready.conf` and check `fail2ban-client status serviceready`.

The sample jail is disabled until configured. Installation does not automatically change firewall rules. Ensure log rotation is configured for the service error log.

The limiter and events use the server's REMOTE_ADDR, never arbitrary X-Forwarded-For headers. Behind a reverse proxy, configure the WSGI server to accept client IP forwarding only from explicit trusted proxies; otherwise all clients share the proxy's limit. Configure Fail2ban at the edge where the real client IP can be blocked. Shared NAT clients also share an IP budget.

Tests cover simultaneous reservations, persistence, expiry, independent IP/MFA budgets, actual endpoint 429 responses and safe log contents. Live firewall bans require verification on the deployment host.
