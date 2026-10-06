"""Prepare a DHCP appliance overlay and optionally run an existing OpenWrt ImageBuilder."""
import argparse,json,pathlib,shutil,subprocess,tarfile,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
def packages(provider):
    values=[v.strip() for v in (ROOT/'deploy/openwrt/packages.txt').read_text().splitlines() if v.strip() and not v.startswith('#')]
    if provider in ('vmware','both'):values+=['open-vm-tools']
    if provider in ('virtualbox','both'):values+=['kmod-serviceready-vboxguest','serviceready-vbox-tools']
    return values

def overlay(bundle,destination,provider):
    if destination.exists():raise ValueError('Choose a new overlay directory.')
    with tempfile.TemporaryDirectory() as folder:
        stage=pathlib.Path(folder)
        with tarfile.open(bundle) as archive:
            for item in archive.getmembers():
                path=pathlib.PurePosixPath(item.name)
                if path.is_absolute() or '..' in path.parts or not (item.isfile() or item.isdir()):raise ValueError('Unsafe bundle member.')
                if item.size>64*1024**2:raise ValueError('Oversized bundle member.')
            for item in archive.getmembers():
                target=stage/item.name
                if item.isdir():target.mkdir(parents=True,exist_ok=True)
                else:
                    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.extractfile(item).read());target.chmod(0o644)
        source=stage/'serviceready-openwrt'
        destination.mkdir(parents=True);runtime=destination/'opt/serviceready';runtime.mkdir(parents=True)
        shutil.copytree(source/'app',runtime/'app')
        shutil.copyfile(source/'deploy/account-broker.py',runtime/'account-broker.py')
        shutil.copyfile(source/'deploy/openwrt/host-provider.py',runtime/'openwrt-host.py')
        shutil.copyfile(source/'deploy/openwrt/bootstrap.py',runtime/'openwrt-bootstrap.py')
        shutil.copyfile(source/'deploy/openwrt/menu.sh',runtime/'openwrt-menu.sh')
        shutil.copyfile(source/'deploy/openwrt/menu-apply.py',runtime/'openwrt-menu.py')
        console=destination/'usr/sbin';console.mkdir(parents=True)
        (console/'insap-setup').write_text('#!/bin/sh\nexec sh /opt/serviceready/openwrt-menu.sh "$@"\n');(console/'insap-setup').chmod(0o755)
        init=destination/'etc/init.d';init.mkdir(parents=True)
        for name in ('serviceready','serviceready-accounts','serviceready-proxy'):
            target=init/name;shutil.copyfile(source/'deploy/openwrt'/f'{name}.init',target);target.chmod(0o755)
        defaults=destination/'etc/uci-defaults';defaults.mkdir(parents=True)
        script=defaults/'95-serviceready'
        script.write_text('''#!/bin/sh
# Image-only network profile: eth0 LAN obtains its address from the existing network.
uci set network.lan.proto='dhcp'
uci -q delete network.lan.ipaddr
uci -q delete network.lan.netmask
uci -q delete network.lan.gateway
uci set network.lan6='interface'
uci set network.lan6.device='@lan'
uci set network.lan6.proto='dhcpv6'
uci set network.lan6.reqaddress='try'
uci set network.lan6.reqprefix='no'
uci commit network
# This appliance is a DHCP client, never a competing router/DHCP server.
uci set dhcp.lan.ignore='1'
uci set dhcp.lan.ra='disabled'
uci set dhcp.lan.dhcpv6='disabled'
uci commit dhcp
/etc/init.d/nginx disable
PYTHONPATH=/opt/serviceready/app python3 /opt/serviceready/openwrt-bootstrap.py || exit 1
exit 0
''');script.chmod(0o755)
        # Persist application identity and account settings across attended sysupgrade.
        (destination/'etc/sysupgrade.conf').write_text('/etc/serviceready/\n')
        (destination/'etc/serviceready-image.json').write_text(json.dumps({'provider':provider,'network':'DHCP','setup':'web','packages':packages(provider)},indent=2)+'\n')
    return destination
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',type=pathlib.Path,required=True);parser.add_argument('--overlay',type=pathlib.Path,required=True);parser.add_argument('--provider',choices=['none','vmware','virtualbox','both'],default='both');parser.add_argument('--imagebuilder',type=pathlib.Path);parser.add_argument('--rootfs-mb',type=int,default=128);args=parser.parse_args()
    if args.rootfs_mb<64:parser.error('Reserve at least 64 MB until image size is measured.')
    if args.imagebuilder:
        # Fail early rather than silently dropping requested VirtualBox support.
        info=subprocess.check_output(['make','info'],cwd=args.imagebuilder,text=True)
        if 'x86/64' not in info:parser.error('Use the current stable x86/64 ImageBuilder.')
        if args.provider in ('virtualbox','both'):
            names={p.name for p in (args.imagebuilder/'packages').glob('*')}
            for package in ('kmod-serviceready-vboxguest','serviceready-vbox-tools'):
                if not any(n.startswith(package+'-') for n in names):parser.error('Provide the matching SDK-built '+package+' package in ImageBuilder/packages first. See docs/OPENWRT.md.')
    overlay(args.bundle,args.overlay,args.provider)
    if args.imagebuilder:
        selected=' '.join(packages(args.provider)+['-luci','-luci-ssl','-uhttpd','-uhttpd-mod-ubus'])
        subprocess.run(['make','image','PROFILE=generic','FILES='+str(args.overlay.resolve()),'PACKAGES='+selected,'CONFIG_TARGET_ROOTFS_PARTSIZE='+str(args.rootfs_mb)],cwd=args.imagebuilder,check=True)
    print('Overlay: '+str(args.overlay));print('Packages: '+' '.join(packages(args.provider)))
