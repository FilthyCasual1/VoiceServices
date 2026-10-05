# Architecture and integration roadmap

## Deployment baseline

All compute is x86 on VMware ESXi. CUCM, Unity Connection, and IM and Presence target 12.5; exact maintenance releases, hypervisor compatibility, licenses, and 79xx firmware remain to be selected. No HWIC, EHWIC, or UCS-E dependency remains. WAN links are managed Wi-Fi-client and WWAN equipment, with OpenWrt and SNMP/API control as their interfaces allow.

The visual reference is an appliance portal around 2006: compact blue header, text tabs, no redundant sidebar, white pages, gray tables, small Arial/Tahoma text, plain forms. Do not introduce a modern card dashboard or replace native Cisco administration interfaces.

Utilities (calculator, RSS, weather, flights) execute only on phones. The web portal supplies configuration and availability, not utility screens.

The public landing portal requires no login. Edits and private user data require authentication; native application links defer authorization to their destinations.

## Identity boundary

Users own profiles; phones own capabilities and location. Stable internal identity links CUCM user/device profiles, CUC mailbox IDs, and application roles. Native CUCM Extension Mobility remains authoritative for telephone login; a verified native session must precede application binding in the completed integration. CUCM native EM API is separate from AXL provisioning and JTAPI call events.

The development build uses manually issued, short-lived application tokens. Tokens do not authorize changes to Cisco systems. Every new terminal binding invalidates the user's old binding, and rebinding a terminal invalidates its previous occupant. Application logout is separate from web logout and native EM logout. Production orchestration must reconcile native logout, terminal reboots, timeouts, and login failures, and clear private screen/widget state on the former phone. Never infer administrator privileges from IP, MAC, extension, or a URL username.

CUCM owns calling privileges through its own configuration. The application owns app/management privileges and enforces them server-side. CUC mailbox authorization remains distinct. Model-specific button capacity and XML objects cannot roam literally; render the same user data for the terminal's capabilities.

## Adapters to implement

| Adapter | Responsibilities | Validation gate |
|---|---|---|
| CUCM AXL | Inventory, provisioning, user and device-profile mapping | Use 12.5 schema; reconcile existing objects; validate credentials and role scope |
| CUCM EM | Login/logout orchestration, confirmed user/device bindings | Real profile moves, native logout, stale session revocation |
| CUCM JTAPI | Current-call context and call events | Multiple calls, transfers, privacy flags, original dialed vs connected number |
| CUC CUPI/CUMI | Provisioning, mailbox access, message metadata | Per-user access; CUC does not supply CUE VoiceView Express |
| IM&P | User enablement and observed health | Identify supported 12.5 interfaces and CUCM dependencies |
| WAN | SNMP monitoring and available write/API operations | Wi-Fi is upstream client, not local AP; writable MIB coverage is not assumed |
| Feeds/weather/flights | Provider fetch, normalization, caching | Upstream HTTPS, rate limits, stale timestamps; SSRF-resistant fetch policy |
| Recording | Capture control, catalog, storage, playback | Both RTP directions, compatible codecs, actual phone BiB support or gateway capture |

External adapters should report `unconfigured`, `configured/unverified`, `reachable`, `degraded`, or `failed`, with a last-observed timestamp. A configured URL is not a health check. Credentials must be deployment secrets, never browser-visible config or phone XML.

## Cross-system operations

Use a durable job journal and per-step results for provisioning. CUCM + CUC + application changes are not an atomic transaction. Verify resulting native state, expose partial completion, and provide deliberate retry/compensation. Import native inventory before creating replacements. Do not overwrite native edits silently.

## Directory and call context

The SQLite directory is implemented. Future CTI integration enables Services → Save current number → prefilled name/number form → personal/shared save. Multiple calls require call selection. Preserve original dial string and normalized number; never guess an outside-line prefix. Partial digits before call initiation require explicit testing. Private/unknown caller IDs must not be replaced with fabricated values. Server-side call history provides portable history rather than relying on handset-local records.

## Status widget

One compositor owns `CiscoIPPhoneStatus` / `CiscoIPPhoneStatusFile`. It renders network state, active uplink, warnings, and confirmed recording state, replacing the existing object. It uses authenticated push; the widget is on the Call plane, not every screen. Exact model support and sizing require handset tests. Clear with `Init:AppStatus` on sign-out. Prioritize alerts centrally so individual apps do not overwrite one another. Never show REC before capture acknowledgement. Account for stale displays after server failure.

## Recording and playback

Use an actual recorder/media service. CUCM controls/metadata are not audio capture. Select BiB-based capture only for verified phones; alternative capture may use a separate gateway or an anchored media server. Both internal and external recording scope must be designed and tested. On-demand capture begins when enabled; retrospective whole-call recording requires prior capture/buffering.

Store call ID, owner, participants, timestamps, capture state, file references, retention policy, and playback authorization. Web playback requires authenticated byte-range delivery. Phone playback can use an authorized short-lived playback session through a normal call, or supported XML/RTP features after testing. Keep recorded calls distinct from CUC voicemail. Playback and export permissions are checked independently; file paths are never accepted directly from clients.

## Delivery stages

1. **Implemented:** portal, local identity, contacts, calculator, preferences, development bindings, XML framework, configurable native links/download listings.
2. **Native identity:** CUCM inventory/AXL and EM reconciliation; replace manual bindings; add integration secret management and managed configuration UI.
3. **Call context:** JTAPI, save-current-number, server call history, phone-side contact editing and paginated search.
4. **Information apps:** RSS, weather, flights, cache workers and server-generated compatible graphics.
5. **Operations:** WAN status/control, authenticated widget compositor, CUC and IM&P workflows.
6. **Media:** actual recording backend, recording catalog, browser and phone playback.

Only stage 1 is completed. No real Cisco, OpenWrt, WAN, upstream-provider, or recording integration has been validated.

## User-editable line keys

Portal Phone Customization links to native CUCM Self Care for available speed-dial and label settings. It does not claim that all line appearances are editable in Self Care. A future custom key editor must identify the user's owned phone or active EM profile, retrieve the assigned phone button template, and expose only policy-permitted slots and actions. Phone capability and shared-line impact must be validated. Restrict speed-dial changes separately from extension assignments, BLF configuration, and template changes. Apply edits to the roaming profile when appropriate, verify native state, and explain any phone reset needed. No live custom line-key writes are implemented.
