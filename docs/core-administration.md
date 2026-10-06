# Core administration (1.12.2)

These controls are part of the permanent core and work without any addons.

**Overview** reports the portal hostname and uptime, local disk and memory,
system load, account/session counts, and every supported addon. Repositories show
file counts; FTP/PXE show fresh worker heartbeat status when available. ESXi and
other external connections remain explicitly unverified until queried through
their own addons. Local resource measurements describe the portal host, not ESXi.

**Branding** changes the title and subtitle across the masthead, browser tabs,
page headings and footer. The default subtitle is `ServiceReady INSAP`. Upload a
PNG or JPEG logo (at most 1 MiB); choose the default arrow to reset it. SVG and
HTML uploads are not accepted. The masthead system field always shows the host
hostname. Standard users see `Hello, Name.` using their display name, or username
if blank. Administrators see their username and access level. Guests see Sign in.
Display names can be changed in My Account.

**Home page blocks** lets administrators add, edit, hide, reorder and remove blocks.
Lower position numbers appear first. Text is escaped, with line breaks preserved;
optional links must be relative portal links or HTTP(S) addresses. A block can
require a particular installed addon. Empty lists stay empty after restart, and
default blocks are seeded only once. This editor uses inline forms and normal
page submissions; no raw JSON or HTML editing is required.

**Users and passwords** creates accounts with a selected portal role and optional
display name. Passwords require at least 12 characters. Existing users can be
promoted/demoted or deleted; role changes revoke sessions and phone bindings.
Deletion requires confirmation, removes personal contacts and login sessions,
and cannot target the signed-in account or remove the last administrator.
My Account handles the current user's password and display name.

On Alpine, creation/deletion is performed through the root-owned account broker.
Only enrolled accounts with UID at least 1000 are eligible for deletion; system
accounts and unenrolled accounts are refused. Account deletion preserves any
home directory. Portal administrator roles do not grant operating-system root
access. Broker integration has policy/mock tests but still needs real Alpine
validation. OS and portal database deletion cannot be one atomic transaction.

Appearance → Date, time and time zone sets the portal-wide IANA timezone and date/time presets (ISO, day-first, month-first or named dates; 12/24-hour time with optional seconds). Inbox and session timestamps and time-based greetings follow these settings. Update schedules use `portal` to inherit the global timezone; changing it recalculates their next occurrence. Explicit schedule timezone overrides remain in effect. These settings format portal data and do not change the host OS clock.

Overview refreshes local measurements every five seconds while visible. Portal navigation preserves the masthead and unchanged images; ordinary full-page navigation remains available without JavaScript. Host OEM identity comes from readable Linux DMI information: manufacturer, model, serial number, system board and BIOS. Missing or restricted fields are omitted. Virtual machines report the identity exposed by the hypervisor, rather than the physical ESXi server.

Home page blocks are grouped into Guest home and Signed-in home. Each block belongs to one audience; the portal chooses the home automatically from the session. Existing blocks migrate to Guest home, and service blocks are copied once to Signed-in home with a My Account link. Edits and removal are independent thereafter.
