# Downloads and network deployment

ServiceReady 0.5.0 separates internal application distribution from voice features.
Upload the separate **Downloads** package in Administration > Addons.
New deployments start without addons. Administrators can upload packages or add HTTP(S) catalog
links with title, version and platform in Administration > Downloads. Guests can
retrieve published packages. Publish only artifacts intended for your internal
network; removal hides the catalog and disables file routes without deleting data.
Uploads use the same bounded streaming and checksum handling as the update addon.

## PXE and Image Deployment

Install the separate addon, then open Administration > PXE and images. Upload
`ipxe.efi` and `undionly.kpxe` from an official iPXE build, plus your boot assets.
Add an ISO profile using its HTTP URL, or a Clonezilla restoration profile with
matching `vmlinuz`, `initrd.img` and `filesystem.squashfs` from the same live release.
The boot-assets table gives URLs and SHA-256 hashes. Assets support byte-range
HTTP requests. The generated menu is `/pxe/boot.ipxe`.

For restoration, provide an existing NFS image repository, or select a repository
interactively at the booted machine. This addon does not provide an NFS server.
Restoration prompts for image and target disk and retains Clonezilla confirmation;
it is not an unattended wipe workflow.

On Alpine, rerun the installer to install the OpenRC PXE supervisor and dnsmasq.
Configure a fixed IPv4 server address and directly connected deployment subnet.
Enable proxy-DHCP/TFTP only after uploading both bootloaders. The worker supplies
BIOS and x86-64 UEFI boot details alongside an existing DHCP server; it does not
allocate client addresses. Permit UDP 67, 69, 4011 and TFTP transfer traffic, plus
the portal's HTTP port on that network. Keep the deployment network isolated.
Removing the addon stops its worker listener; profiles and files are retained.
Inspect `/var/log/serviceready-pxe.log` when boot services fail. Configuration being
enabled is not proof that a client has booted successfully.

HTTP ISO SAN boot depends on image and firmware compatibility and does not boot
every ISO. Windows installation generally needs a WinPE/wimboot workflow, which
this release does not implement. Secure Boot requires compatible signed loaders
or a lab firmware configuration that permits the supplied iPXE build.

Tests cover generated menus, input validation, module removal, public file delivery
and ranges. Actual BIOS/UEFI PXE boot, Alpine networking and disk restoration must
still be validated on the ESXi testbed before use on machines with valuable data.

References: [iPXE sanboot](https://ipxe.org/cmd/sanboot),
[iPXE wimboot](https://ipxe.org/wimboot),
[Clonezilla customized PXE](https://clonezilla.org/show-live-doc-content.php?topic=clonezilla-live%2Fdoc%2F07_Customized_script_with_PXE),
[dnsmasq proxy PXE options](https://thekelleys.org.uk/dnsmasq/docs/dnsmasq-man.html).
