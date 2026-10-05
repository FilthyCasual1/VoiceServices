"""Root-owned supervisor for the optional dnsmasq proxy-DHCP/TFTP process."""
import argparse
import ipaddress
import json
from pathlib import Path
import subprocess
import signal
import time
from .core import Store
from .modules import Modules

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);args=parser.parse_args()
    with open(args.config) as source: config=json.load(source)
    store=Store(config['database']);modules=Modules(store)
    root=Path(config.get('pxe_directory',str(Path(store.path).parent/'pxe')))
    def stop(signum,frame): raise SystemExit(0)
    signal.signal(signal.SIGTERM,stop)
    process=None;previous=None
    try:
        while True:
            with store.connect() as db:
                db.execute('CREATE TABLE IF NOT EXISTS pxe_settings(id INTEGER PRIMARY KEY,settings TEXT)')
                row=db.execute('SELECT settings FROM pxe_settings WHERE id=1').fetchone()
                settings=json.loads(row[0]) if row and modules.installed('pxe') else None
            if settings!=previous:
                if process: process.terminate();process.wait(timeout=5);process=None
                previous=settings
                if settings and settings.get('enabled'):
                    network=ipaddress.IPv4Network(settings['subnet'],strict=True);address=ipaddress.IPv4Address(settings['address'])
                    if address not in network: raise ValueError('Invalid deployment network.')
                    base=config['public_url'].rstrip('/')
                    from .pxe import url
                    url(base+'/pxe/boot.ipxe')
                    process=subprocess.Popen(['/usr/sbin/dnsmasq','--no-daemon','--conf-file=/dev/null','--port=0','--user=serviceready','--group=serviceready','--enable-tftp','--tftp-root='+str(root),'--listen-address='+str(address),'--bind-interfaces','--dhcp-range='+str(network.network_address)+',proxy,'+str(network.netmask),'--dhcp-match=set:efi64,option:client-arch,7','--dhcp-match=set:efi64,option:client-arch,9','--dhcp-userclass=set:ipxe,iPXE','--pxe-service=tag:!ipxe,x86PC,ServiceReady,undionly.kpxe,'+str(address),'--pxe-service=tag:!ipxe,BC_EFI,ServiceReady,ipxe.efi,'+str(address),'--pxe-service=tag:!ipxe,x86-64_EFI,ServiceReady,ipxe.efi,'+str(address),'--dhcp-boot=tag:ipxe,'+base+'/pxe/boot.ipxe','--dhcp-boot=tag:!ipxe,tag:efi64,ipxe.efi,serviceready,'+str(address),'--dhcp-boot=tag:!ipxe,tag:!efi64,undionly.kpxe,serviceready,'+str(address)],stdout=subprocess.DEVNULL)
            if process and process.poll() is not None: raise RuntimeError('PXE service failed. Check network settings and ports.')
            time.sleep(.5)
    finally:
        if process and process.poll() is None: process.terminate();process.wait(timeout=5)

if __name__=='__main__': main()
