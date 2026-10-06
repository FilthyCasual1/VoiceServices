# Receive-only SMTP notifications

Upload `smtp-notifications-1.13.3.sraddon` through Administration → System → Addons. Its SMTP page appears only while installed. The listener is initially disabled. Uninstall removes the implementation and stops receiving mail; saved settings and delivered inbox messages remain.

The Alpine installer includes aiosmtpd 1.4.6 and the `serviceready-smtp` OpenRC supervisor. Existing installations gain these through INSAP update. Other hosts can install the optional dependency with `pip install '.[smtp]'` and supervise `python -m voiceservices.smtp_service --config config.json`. The voice addon is not required.

Set the listen IP, port, trusted application networks and recipient routes. The default is loopback port 2525. Alpine's privileged worker can bind port 25, then drops to the ServiceReady account before accepting mail. Incoming SMTP uses source-IP authorization without SMTP AUTH. It neither sends nor relays email.

Routes have one address and one portal username per line:

```
alerts@services.example | admin
voice@services.example | operator
```

Configure applications with the portal's reachable SMTP address, selected port and a mapped recipient address. Unknown recipients and untrusted application IPs are rejected. Optional STARTTLS uses `smtp_tls_cert` and `smtp_tls_key` paths in the host configuration. Check each application's supported port and encryption options in your testbed.

Email subject and plain text become an inbox notification. `X-Priority: 1` or `2`, or `Importance: high`, maps to Urgent; `X-Priority: 3` maps to Caution; otherwise Info. HTML-only emails get an explanatory inbox entry; attachments are not stored. Limits are 1 MiB per message and 50 recipients. Inbox writes commit before SMTP acceptance; senders must retry temporary delivery failures. An interrupted SMTP acknowledgement may cause a duplicate, as with ordinary SMTP.

Tests use an actual local SMTP session for receipt, priority mapping, unknown-recipient rejection and rejection after uninstall. Trusted source checks are also tested. Cisco appliance integration and Alpine privileged service startup still require testbed validation.
