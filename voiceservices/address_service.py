"""Root-owned installer-managed Caddy sites follow local DHCP/static addresses."""
import json,os,subprocess,tempfile,time
from pathlib import Path
from .network_address import Addresses,origin,caddy_config
CONFIG=Path('/etc/serviceready/config.json');CADDY=Path('/etc/caddy/Caddyfile')
def refresh(addresses):
    config=json.loads(CONFIG.read_text())
    if not config.get('automatic_public_url'):
        if config.get('tls_proxy')=='nginx':
            from .rocky_tls import configure
            configure(config,addresses)
        return
    values,primary=addresses.current()
    if not primary:return # Keep the last configuration while networking is unavailable.
    if config.get('tls_proxy')=='nginx':
        from .rocky_tls import configure
        configure(config,addresses)
    elif config.get('automatic_local_tls'):
        text=caddy_config(values,primary,config.get('listen_port',8080))
        old=CADDY.read_text()
        if not old.startswith('# ServiceReady managed address configuration\n'):raise ValueError('Caddyfile is no longer managed by ServiceReady.')
        if text!=old:
            fd,name=tempfile.mkstemp(prefix='serviceready-',suffix='.Caddyfile',dir=str(CADDY.parent))
            try:
                with os.fdopen(fd,'w') as file:file.write(text)
                subprocess.run(['caddy','validate','--config',name,'--adapter','caddyfile'],check=True,timeout=30,stdout=subprocess.DEVNULL)
                os.chmod(name,0o644);os.replace(name,CADDY)
                try:subprocess.run(['caddy','reload','--config',str(CADDY),'--adapter','caddyfile'],check=True,timeout=30)
                except Exception:CADDY.write_text(old);raise
            finally:
                if os.path.exists(name):os.unlink(name)
    url=origin(config,primary)
    if config.get('public_url')!=url:
        metadata=CONFIG.stat();config['public_url']=url
        fd,name=tempfile.mkstemp(prefix='address-',dir=str(CONFIG.parent))
        try:
            with os.fdopen(fd,'w') as file:
                os.fchown(file.fileno(),metadata.st_uid,metadata.st_gid)
                os.fchmod(file.fileno(),metadata.st_mode&0o777)
                json.dump(config,file,indent=2)
            os.replace(name,CONFIG)
        finally:
            if os.path.exists(name):os.unlink(name)
    return url
def main():
    if os.geteuid()!=0:raise SystemExit('Address service requires the installed root service.')
    addresses=Addresses()
    while True:
        try:refresh(addresses)
        except Exception as error:print('Address refresh failed: '+str(error),flush=True)
        time.sleep(15)
if __name__=='__main__':main()
