# Host configuration

Rocky Linux 10 host controls are part of the core. Maintenance and the OS-account terminal no longer require an addon. OS/INSAP updates remain on Overview; scheduled updates use Update schedules.

Network and time configures an active NetworkManager connection's IPv4 DHCP or static address, gateway and DNS; an optional hostname sets the system hostname. Leave hostname blank to preserve the host's existing policy, including DHCP-provided names. The masthead reads the current system hostname on every request. Automatic portal addressing follows interface address changes; a manually configured portal origin remains fixed.

Network changes require a local administrator password and HTTPS. Reconnect at the new address and confirm within 90 seconds. Otherwise a cloned previous connection becomes active and persists across reboot. The failed profile remains with autoconnect disabled, for inspection. IPv6 is retained. NTP sources are managed through chrony, independently of the portal's display timezone.

Upload storage lists disks and accepts only blank, unused whole disks without partitions, filesystems, mounts or signatures. Enter `FORMAT /dev/<disk>` and your administrator password. Formatting permanently creates an ext4 filesystem on that disk; verify its model and size first. Existing downloads, FTP update packages, PXE images, uploaded branding and profile photos migrate to `/srv/serviceready-data`. Upload buffers use that volume too. The UUID mount is persisted in fstab with `nofail`; missing/wrong disks block upload content instead of filling the boot disk. Core accounts and configuration remain available.

Application code, addons, settings, inbox metadata, account database, host logs and OS packages remain on the boot volume. The volume is not a general NAS share. A missing volume can be replaced with a new blank disk through the same form. This does not recover the old files; metadata is retained. Existing-volume adoption is not supported by this initial setup form. Formatting/migration and actual NetworkManager changes must be validated in the test VM before production use.
