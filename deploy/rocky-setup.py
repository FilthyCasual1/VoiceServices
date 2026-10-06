"""Installer configuration and startup verification for Rocky Linux 10."""
import argparse,json,ssl,time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
from voiceservices.network_address import Addresses,origin

def configuration(url,template):
    automatic=not url.strip();addresses=Addresses();_,primary=addresses.current()
    if not primary:raise ValueError('No active host address. Configure networking first.')
    url=origin({'public_url':'https://localhost'},primary) if automatic else url.strip().rstrip('/')
    parsed=urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.port not in (None,443) or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError('Use an HTTPS origin on port 443, or Enter for the current address.')
    config=json.loads(template.read_text())
    config.update(public_url=url,public_port=443,secure_cookies=True,automatic_public_url=automatic,automatic_local_tls=True,tls_proxy='nginx',trusted_proxy='127.0.0.1',auth_backend='system',account_socket='/run/serviceready-accounts/socket',listen_host='127.0.0.1',listen_port=8080,database='/var/lib/serviceready/serviceready.sqlite3',addon_directory='/var/lib/serviceready/addons',update_directory='/var/lib/serviceready/updates')
    return config

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['config','proxy','verify']);parser.add_argument('--url',default='');parser.add_argument('--update',action='store_true');parser.add_argument('--template',default='config.bare.json');args=parser.parse_args()
    path=Path('/etc/serviceready/config.json')
    if args.action=='config':
        if path.exists() and not args.update:print('Retaining existing configuration.');return
        config=configuration(args.url,Path(args.template))
        if path.exists():
            existing=json.loads(path.read_text())
            for key in ('public_url','public_port','secure_cookies','automatic_public_url','automatic_local_tls','tls_proxy','listen_host','listen_port'):existing[key]=config[key]
            config=existing
        path.write_text(json.dumps(config,indent=2));path.chmod(0o640);print('Portal URL: '+config['public_url']);return
    config=json.loads(path.read_text())
    if args.action=='proxy':
        from voiceservices.rocky_tls import configure
        configure(config,Addresses(),reload=False);return
    context=ssl.create_default_context(cafile='/etc/serviceready/tls/ca.crt')
    for attempt in range(30):
        try:
            for url in ('http://127.0.0.1:8080/healthz',config['public_url']+'/healthz'):
                with urlopen(url,context=context,timeout=3) as response:
                    if json.load(response).get('status')!='running':raise ValueError('Unexpected health response.')
            print('HTTP and certificate-verified HTTPS health checks passed.\nPortal: '+config['public_url']);return
        except Exception:
            if attempt==29:raise
            time.sleep(1)
if __name__=='__main__':main()
