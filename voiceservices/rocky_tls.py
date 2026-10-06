"""Managed Rocky Nginx proxy and local CA certificates with IP SANs."""
import ipaddress,json,re,secrets,subprocess,tempfile
from pathlib import Path
MARKER='# ServiceReady managed nginx configuration\n'
def run(command):subprocess.run(command,check=True,timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
def configure(config,addresses,reload=True,root=Path('/')):
    values,primary=addresses.current()
    if not primary:raise ValueError('No active network address found.')
    values=[str(ipaddress.ip_address(value)) for value in values]
    host=__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(config['public_url']).hostname
    sans=['IP:'+value for value in values]
    if host and host not in values:
        try:ipaddress.ip_address(host)
        except ValueError:
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*',host):raise ValueError('Invalid HTTPS hostname.')
            sans.append('DNS:'+host)
    ca=root/'etc/serviceready/tls';ca.mkdir(parents=True,exist_ok=True,mode=0o700);ca.chmod(0o700)
    key=root/'etc/pki/tls/private/serviceready.key';cert=root/'etc/pki/tls/certs/serviceready.crt'
    proxy=root/'etc/nginx/conf.d/serviceready.conf'
    for path in (key.parent,cert.parent,proxy.parent):path.mkdir(parents=True,exist_ok=True)
    if proxy.exists() and not proxy.read_text().startswith(MARKER):raise ValueError('Nginx configuration is not installer-managed.')
    if not (ca/'ca.key').exists() and not (ca/'ca.crt').exists():
        run(['openssl','req','-x509','-newkey','rsa:3072','-nodes','-days','3650','-sha256','-subj','/CN=ServiceReady Local CA','-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign','-keyout',str(ca/'ca.key'),'-out',str(ca/'ca.crt')])
        (ca/'ca.key').chmod(0o600);(ca/'ca.crt').chmod(0o644)
    if not (ca/'ca.key').is_file() or not (ca/'ca.crt').is_file():raise ValueError('Local CA is incomplete; restore its backup before continuing.')
    target=MARKER+'server {\n    listen 443 ssl default_server;\n    listen [::]:443 ssl default_server;\n    server_name _;\n    ssl_certificate '+str(cert)+';\n    ssl_certificate_key '+str(key)+';\n    ssl_protocols TLSv1.2 TLSv1.3;\n    client_max_body_size '+str(int(config.get('update_upload_limit',8*1024**3))+16384)+';\n    location / {\n        proxy_pass http://127.0.0.1:'+str(int(config.get('listen_port',8080)))+';\n        proxy_set_header Host $http_host;\n        proxy_set_header X-Forwarded-Proto https;\n        proxy_set_header X-Forwarded-For $remote_addr;\n        proxy_read_timeout 3600s;\n    }\n}\n'
    state=ca/'addresses.json';signature=json.dumps(sorted(sans))
    changed=not cert.exists() or not key.exists() or not state.exists() or state.read_text()!=signature
    if not changed:
        check=subprocess.run(['openssl','x509','-checkend','604800','-noout','-in',str(cert)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        changed=check.returncode!=0
    changed=changed or not proxy.exists() or proxy.read_text()!=target
    if not changed:return
    previous={p:p.read_bytes() if p.exists() else None for p in (key,cert,proxy,state)}
    try:
        with tempfile.TemporaryDirectory(dir=str(ca)) as temporary:
            temp=Path(temporary);(temp/'extensions').write_text('subjectAltName='+','.join(sans)+'\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n')
            run(['openssl','req','-new','-newkey','rsa:2048','-nodes','-subj','/CN=ServiceReady','-keyout',str(temp/'key'),'-out',str(temp/'request')])
            run(['openssl','x509','-req','-in',str(temp/'request'),'-CA',str(ca/'ca.crt'),'-CAkey',str(ca/'ca.key'),'-set_serial','0x'+secrets.token_hex(16),'-days','90','-sha256','-extfile',str(temp/'extensions'),'-out',str(temp/'certificate')])
            key.write_bytes((temp/'key').read_bytes());key.chmod(0o600)
            cert.write_bytes((temp/'certificate').read_bytes());cert.chmod(0o644)
        proxy.write_text(target);proxy.chmod(0o644)
        if root==Path('/'):
            run(['restorecon',str(key),str(cert),str(proxy)])
            run(['nginx','-t'])
            if reload:run(['systemctl','reload','nginx'])
        state.write_text(signature)
    except Exception:
        for path,data in previous.items():
            if data is None:path.unlink(missing_ok=True)
            else:path.write_bytes(data)
        raise
