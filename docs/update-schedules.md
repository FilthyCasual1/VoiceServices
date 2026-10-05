# Automatic updates

Administration → System Operator → Update schedules configures independent daily or weekly portal and operating-system updates, local time, weekday and IANA timezone. Both schedules are off by default. The page shows next occurrence, last result, provider availability and scheduler heartbeat.

The Alpine installer registers the unprivileged `serviceready-scheduler` OpenRC service. Existing installations receive it through INSAP update. On other hosts, supervise `python -m voiceservices.schedule_service --config config.json`; execution also requires a supported host update provider. The current execution provider is Alpine's existing approved privileged broker. Saving a schedule in a preview without that provider does not perform any upgrade.

Schedules and run claims persist in SQLite. When service resumes after downtime, a missed occurrence is attempted once, then the next future occurrence is calculated. Running updates defer other due jobs; a persistent 60-second dispatch gap avoids startup overlap. Each due job is claimed before dispatch; a crash in that gap may skip that occurrence rather than rerun an upgrade. Failed requests remain visible and wait for the next occurrence. Manual updates remain available on Overview.

Portal updates briefly restart services and use the approved main branch with existing backups and settings preservation. OS updates upgrade installed packages without automatic reboot. Nonexistent daylight-saving times are skipped; repeated local times run once. Choose a quiet maintenance window.

Tests verify timezone calculations, DST gaps, persistence, disabled schedules, busy-provider deferral and dispatch deduplication with a mocked update broker. Actual scheduled OS/portal upgrades require Alpine testbed validation.
