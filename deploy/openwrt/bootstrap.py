#!/usr/bin/env python3
"""Initialize an OpenWrt appliance at first boot; never embeds administrator credentials."""
import argparse,json,os,pathlib,pwd,secrets,subprocess
ROOT=pathlib.Path('/')
def command(args):subprocess.run(args,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
def configuration(port=443):
    if not 1<=port<=65535:raise ValueError('Invalid HTTPS port.')
    return {'database':'/etc/serviceready/state/serviceready.sqlite3','addon_directory':'/etc/serviceready/state/addons','public_url':'https://127.0.0.1'+(':'+str(port) if port!=443 else ''),'public_port':port,'listen_host':'127.0.0.1','listen_port':8080,'trusted_proxy':'127.0.0.1','secure_cookies':True,'auth_backend':'system','account_socket':'/run/serviceready-accounts/socket','automatic_public_url':True,'tls_proxy':'openwrt','first_boot_setup':True,'initial_modules':[],'update_directory':'/tmp/serviceready/updates','update_upload_limit':64*1024**2,'server_threads':2,'connection_limit':32,'channel_timeout':30,'security':{'registration_enabled':False}}
def bootstrap(port=443):
    if os.geteuid()!=0 or not pathlib.Path('/etc/openwrt_release').exists():raise ValueError('Run on OpenWrt as root.')
    import grp
    for group in ('serviceready','serviceready-users'):
        try:grp.getgrnam(group)
        except KeyError:command(['groupadd',group])
    try:account=pwd.getpwnam('serviceready')
    except KeyError:
        command(['useradd','--system','--no-create-home','--gid','serviceready','--home-dir','/etc/serviceready/state','--shell','/bin/false','serviceready']);account=pwd.getpwnam('serviceready')
    config_dir=pathlib.Path('/etc/serviceready');config_dir.mkdir(exist_ok=True);os.chown(config_dir,0,account.pw_gid);config_dir.chmod(0o750)
    config_path=config_dir/'config.json'
    if not config_path.exists():config_path.write_text(json.dumps(configuration(port),indent=2)+'\n')
    os.chown(config_path,0,account.pw_gid);config_path.chmod(0o640)
    for folder in (config_dir/'state',pathlib.Path('/tmp/serviceready')):
        folder.mkdir(exist_ok=True);os.chown(folder,account.pw_uid,account.pw_gid);folder.chmod(0o750)
    from voiceservices.core import Store
    store=Store(json.loads(config_path.read_text())['database'])
    with store.connect() as db:pending=db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone() is None
    for path in (config_dir/'state').rglob('*'):
        os.chown(path,account.pw_uid,account.pw_gid);path.chmod(0o750 if path.is_dir() else 0o640)
    token=config_dir/'setup-token'
    if pending and not token.exists():token.write_text(secrets.token_urlsafe(24)+'\n');token.chmod(0o600)
    from voiceservices.openwrt_tls import refresh
    from voiceservices.network_address import Addresses
    config=json.loads(config_path.read_text());config['public_url']=refresh(config,Addresses(),reload=False);config_path.write_text(json.dumps(config,indent=2)+'\n')
    if pending:
        message='\nServiceReady first-boot setup: '+config['public_url']+'/setup\nSetup code: '+token.read_text().strip()+'\n'
        print(message,flush=True)
        with open('/dev/console','w') as console:console.write(message)
    for service in ('serviceready-vbox',):
        if pathlib.Path('/etc/init.d/'+service).exists():command(['/etc/init.d/'+service,'enable'])
    for service in ('serviceready-accounts','serviceready','serviceready-proxy'):command(['/etc/init.d/'+service,'enable'])
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=443);args=p.parse_args();bootstrap(args.port)
