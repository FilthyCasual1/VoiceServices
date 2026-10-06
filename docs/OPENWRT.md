# OpenWrt appliance preparation

Target: current stable OpenWrt **25.12.5**, x86/64 generic. This is a migration preparation kit, not a validated production replacement for the Rocky deployment. Keep the Rocky VM and backups until the new VM passes the acceptance checks below.

## Small runtime

The OpenWrt bundle contains INSAP and pinned pure Python wheels for Waitress, PyOTP and Segno. It uses python3-light plus selected standard-library packages; no target-side pip, virtual environment, Git checkout, compiler, Kerberos build toolchain or unused addon daemon is installed. The portal uses two request threads and a 32-connection limit; Nginx has one worker. Procd supervises the portal, root account broker and dedicated HTTPS proxy. DHCP/TLS tracking shares the broker process. Temporary data uses /tmp and log output goes to logd. Accounts, settings and installed addon metadata are persistent under /etc/serviceready/state. Uploaded content belongs on a separately mounted data disk in the completed storage provider.

The smaller OS does not remove Python’s memory cost. No minimum RAM or final image size is claimed before VM measurements. ImageBuilder reserves 128 MB for the root partition by default; this is a partition allowance, not a measured image size. Use smaller allowances only after checking the build output and free overlay space.

## Build a runtime bundle

From a clean release checkout on a development machine with Python and pip:

```
python3 tools/build_openwrt_bundle.py
```

Output: dist/openwrt/serviceready-openwrt.tar.gz. Downloaded wheels are pinned; their hashes and the exact clean-checkout commit are recorded in bundle.json. A dirty checkout is explicitly marked dirty and does not advertise an exact installed commit. Copy only this bundle to the VM; do not keep the repository and old addon archives on its boot disk.

For an existing OpenWrt VM, extract the trusted release bundle in /tmp, enter serviceready-openwrt, and run:

```
sh install-openwrt.sh
```

It retains existing portal accounts/settings. If LuCI already owns port 443, move that listener or use `sh install-openwrt.sh 8443`. The installer does not change existing network or firewall configuration. The portal listens internally only on loopback and is reached through its dedicated HTTPS proxy. Existing firewall rules must permit the chosen portal port on the intended management interface.

## Prebuilt DHCP images and browser setup

Obtain the official **25.12.5 x86/64 ImageBuilder** and verify its published checksum/signature. Keep the ImageBuilder outside the source checkout. For VMware:

```
python3 tools/build_openwrt_image.py \
  --bundle dist/openwrt/serviceready-openwrt.tar.gz \
  --overlay /tmp/insap-openwrt-files \
  --provider vmware \
  --imagebuilder /path/to/openwrt-imagebuilder
```

The generic x86 first-boot profile changes LAN to DHCP, adds a DHCPv6 client, omits LuCI/uHTTPd, includes INSAP in /opt, and starts its procd services. No Internet access is needed to install INSAP on first boot; dependencies are included by ImageBuilder. Attach the VM’s first LAN adapter to the management network with a DHCP server. The normal generic x86 LAN device mapping is retained; check that mapping for any custom target. Use the resulting combined EFI image for UEFI VMs or the combined legacy image for BIOS VMs, converting it to your hypervisor’s disk format as needed.

Open **https://the-DHCP-address/**. The portal redirects to `/setup`: Welcome → Administrator → Review → Complete. A unique ownership code is generated on that VM’s first boot and shown on its console; it is not shared between image copies. Enter that code in the browser, select a new local OS administrator username/password, portal title and time zone. No default administrator password is embedded. If a fresh image has a blank Linux root-console password, the chosen administrator password secures it as well; an existing root password is retained. Setup serializes creation, checks that no administrator already exists, rejects existing OS usernames, and consumes the code. Subsequent boots go to the normal portal. The current DHCP address is detected per request; certificates track IPv4/IPv6 changes through the root broker. Import that VM’s `/etc/serviceready/tls/ca.crt` into the browser trust store. CA keys never leave the appliance.

Do not configure a DHCP server on the appliance’s management LAN; it is a client on the existing network.

## Guest tools retained in image profiles

`--provider vmware` adds OpenWrt’s native open-vm-tools. `--provider virtualbox` requests the two custom packages below. `--provider both` is the default universal-image profile; `none` is an explicit choice. The image builder refuses to proceed with missing VirtualBox packages rather than silently dropping tools. VMware’s feed-provided daemon startup remains managed by its package; first boot enables the supplied VirtualBox procd service when its packages are present.

- **VMware:** native open-vm-tools, without desktop/FUSE extras unless explicitly needed. Its kernel drivers are supplied by the matching OpenWrt x86 image.
- **VirtualBox:** `deploy/openwrt/sdk/serviceready-vboxguest/Makefile` defines `kmod-serviceready-vboxguest` using Linux’s vboxguest/vboxsf modules. Build this inside the matching full OpenWrt kernel build tree. Kernel ABI/version must match the exact firmware. This is a package recipe requiring build verification.
- **VirtualBox userspace:** `deploy/openwrt/sdk/serviceready-vbox-tools` packages VBoxService and VBoxControl **built for x86-64 musl** from Oracle sources, with their license. These binaries are not supplied or cross-compiled by this preparation kit. The package rejects glibc-interpreter binaries; desktop integration is omitted. Put the resulting signed APKs in the matching ImageBuilder/packages directory. Full dependency and agent compatibility checks remain required. Rocky/Alpine binaries and the raw Oracle tools-CD installer are not used on OpenWrt.

VirtualBox userspace cross-compilation and a real guest boot test remain open work before a both-provider production image can be produced. Existing Rocky VMware/VirtualBox tool support remains intact.

## Host feature migration status

Ready for first-boot validation: core portal, local Linux accounts, browser setup, profile/inbox/appearance, native account PTY, IPv4/IPv6 DHCP reachability, HTTPS and basic cleanup. Addon code can be installed, but enabled network-daemon addons still need procd activation and optional dependency profiles; no unused Python daemons run by default.

Pending native adapters: UCI network/time changes with rollback, UCI/fstab storage/RAID/SMART, guest-tools update workflow, signed INSAP bundle update/rollback, enabled-addon worker orchestration and scheduled upgrades. These host actions explicitly report preparation status. Do not execute NetworkManager, systemd, DNF or OpenRC commands on OpenWrt. OS updates must use firmware/attended sysupgrade, not apk upgrade/opkg upgrade. Use an INSAP-inclusive image for sysupgrade; /etc/serviceready is included in preservation settings, but the new firmware must contain /opt/serviceready and its runtime packages.

## Acceptance before switching

1. Boot two fresh clones and confirm different ownership codes and CA keys. No shared admin credentials.
2. Complete browser setup at each DHCP IP; verify local account authentication, replay rejection and setup closure.
3. Reboot and renew the DHCP lease; verify IP/certificate updates, persistence and portal start without console intervention.
4. Verify VMware tools and VirtualBox agent/driver communication on the actual selected hypervisor. Test host shutdown/restart only after the native host provider supports them.
5. Record idle/loaded RAM, compressed image size and free overlay space. Run a concurrent upload while viewing the UI.
6. Validate data-disk removal, firmware recovery/rollback, addon services and migrated settings before retiring the Rocky VM.

Sources: [current releases](https://downloads.openwrt.org/releases/), [OpenWrt Python packages](https://github.com/openwrt/packages/tree/openwrt-25.12/lang/python/python3), [procd](https://openwrt.org/docs/guide-developer/procd-init-scripts), [firmware upgrade guidance](https://openwrt.org/meta/infobox/upgrade_packages_warning), [open-vm-tools feed](https://github.com/openwrt/packages/tree/openwrt-25.12/utils/open-vm-tools).

## Import as an OVA, or configure from the console

After ImageBuilder produces the combined raw boot disk, package it on the build machine:

```
python3 tools/build_ova.py /path/to/openwrt-combined.img.gz --output /path/to/INSAP.ova
```

This requires qemu-img on the build machine. It produces an OVF descriptor, stream-optimized VMDK and SHA-256 manifest inside the OVA. Import into VMware or VirtualBox, map Management to the existing DHCP network, and boot. Select an EFI output image only when the imported VM is configured to use EFI; the OVA does not force a vendor-specific firmware extension. The default 256 MB RAM/one CPU are initial validation settings, not a proven minimum. Real imports on both hypervisors remain required.

For a console setup flow resembling make menuconfig, run `insap-setup` on the installed appliance. The Whiptail menu offers browser setup/code, DHCP/static management networking, NTP servers and guest-agent status. UCI changes validate input and save protected configuration backups; command failures restore previous settings. Console network changes require keeping the console open and manually verifying reachability; the browser rollback provider is still pending. No compiler is installed to present this menu.
