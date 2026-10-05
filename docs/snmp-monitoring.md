# SNMP monitoring addon

Upload `packages/addons/1.12.0/snmp-1.12.0.sraddon` in Administration → Addons. Configuration appears under System Operator → SNMP monitoring. Uninstall removes executable addon files and the menu while preserving settings and history.

This release supports read-only SNMPv2c GET polling and SNMPv2c traps/informs, following RFC 3416 (https://www.rfc-editor.org/rfc/rfc3416). It does not implement SNMP SET, MIB uploads/walks, SNMPv1 or SNMPv3. Community values are stored locally with portal settings and never echoed in page fields. SNMPv2c is unencrypted: use read-only communities on an isolated management network.

Add devices by name and literal IP address, UDP port, read-only community and up to 32 numeric OIDs. Defaults query sysDescr, sysUpTime and sysName. Results show timestamp, response status and OID values; TimeTicks values are raw hundredths of a second. Polling supports up to 32 devices with four concurrent requests, two-second timeouts and a configurable 15–3600 second interval.

Configure trap listen IP, unprivileged UDP port (default 1162), community and trusted source CIDRs, then enable the service. Configure devices to send notifications to this address/port. For devices requiring port 162, configure a host firewall redirect to 1162; this addon does not change firewall rules. Only sources matching the CIDRs and community are accepted. Trap storage is limited to 20 events per second and the latest 1000 events; the page shows the latest 100. Informs receive an acknowledgement after storage. No outbound traps or user inbox alerts are generated in this release.

On Alpine the installer/update broker registers `serviceready-snmp`, an unprivileged OpenRC worker that waits for addon installation and follows configuration changes. Other hosts can run:

```sh
python -m voiceservices.snmp_service --config /path/to/config.json
```

The overview shows the worker heartbeat. A missing/stale worker is explicitly reported. Network polling runs in the worker, rather than blocking page requests. Listener bind errors appear in the service error log and OpenRC retries the worker. Real Cisco agents and the Alpine deployment still require testbed validation.
