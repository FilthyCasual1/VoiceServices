"""One-shot repair for stale installer-managed HTTPS addresses."""
import json,os,shutil,subprocess,tempfile,time
from pathlib import Path
from voiceservices.network_address import Addresses,origin,caddy_config

def replace(path,text,metadata):
    fd,name=tempfile.mkstemp(prefix='repair-',dir=str(path.parent))
    try:
        with os.fdopen(fd,'w') as file:
            os.fchown(file.fileno(),metadata.st_uid,metadata.st_gid)
            os.fchmod(file.fileno(),metadata.st_mode&0o777)
            file.write(text)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def repair(config_path,caddy_path,backup_root,addresses):
    config=json.loads(config_path.read_text())
    old=caddy_path.read_text()
    if not old.startswith('# ServiceReady managed address configuration\n'):
        raise ValueError('Caddyfile is not installer-managed; no changes made.')
    values,primary=addresses.current()
    if not primary:raise ValueError('No active host address found; no changes made.')
    config_meta=config_path.stat();caddy_meta=caddy_path.stat()
    backup_root.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(backup_root,0o700)
    backup=Path(tempfile.mkdtemp(prefix=time.strftime('%Y%m%d-%H%M%S-'),dir=str(backup_root)))
    shutil.copy2(config_path,backup/'config.json');shutil.copy2(caddy_path,backup/'Caddyfile')
    config.update(automatic_public_url=True,automatic_local_tls=True,secure_cookies=True,listen_host='127.0.0.1')
    config['public_url']='https://'+('['+primary+']' if ':' in primary else primary)
    config['public_port']=443
    fd,staged=tempfile.mkstemp(suffix='.Caddyfile',dir=str(caddy_path.parent))
    try:
        with os.fdopen(fd,'w') as file:file.write(caddy_config(values,primary,config.get('listen_port',8080)))
        subprocess.run(['caddy','validate','--config',staged,'--adapter','caddyfile'],check=True,timeout=30)
        try:
            replace(caddy_path,Path(staged).read_text(),caddy_meta)
            replace(config_path,json.dumps(config,indent=2),config_meta)
            subprocess.run(['caddy','reload','--config',str(caddy_path),'--adapter','caddyfile'],check=True,timeout=30)
        except Exception:
            replace(config_path,(backup/'config.json').read_text(),config_meta)
            replace(caddy_path,old,caddy_meta)
            raise
    finally:
        if os.path.exists(staged):os.unlink(staged)
    return config['public_url'],backup

if __name__=='__main__':
    if os.geteuid()!=0:raise SystemExit('Run as root.')
    try:
        url,backup=repair(Path('/etc/serviceready/config.json'),Path('/etc/caddy/Caddyfile'),Path('/var/backups/serviceready-address-repair'),Addresses())
        print('Portal URL: '+url+'\nBackups: '+str(backup))
    except Exception as error:raise SystemExit('Address repair failed: '+str(error))
