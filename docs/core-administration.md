# Core administration (1.2.3)

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
