"""Dedicated small Nginx proxy on OpenWrt, without changing LuCI configuration."""
import json,ipaddress,subprocess
from pathlib import Path
from .network_address import origin
MARKER='# ServiceReady OpenWrt proxy\n'
def command(args):subprocess.run(args,check=True,timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
def refresh(config,addresses,root=Path('/'),reload=True):
    values,primary=addresses.current();values=values or ['127.0.0.1'];primary=primary or values[0]
    values=[str(ipaddress.ip_address(value)) for value in values]
    directory=root/'etc/serviceready/tls';directory.mkdir(parents=True,exist_ok=True);directory.chmod(0o700)
    key=directory/'server.key';cert=directory/'server.crt';ca_key=directory/'ca.key';ca_cert=directory/'ca.crt'
    signature=json.dumps(sorted(values));state=directory/'addresses.json'
    proxy=root/'etc/serviceready/nginx.conf'
    if proxy.exists() and not proxy.read_text().startswith(MARKER):raise ValueError('OpenWrt proxy configuration is not managed by INSAP.')
    if ca_key.exists()!=ca_cert.exists():raise ValueError('Restore the incomplete portal CA before continuing.')
    if not ca_key.exists():
        command(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:prime256v1','-nodes','-days','3650','-subj','/CN=ServiceReady Local CA','-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign','-keyout',str(ca_key),'-out',str(ca_cert)])
        ca_key.chmod(0o600);ca_cert.chmod(0o644)
    changed=not cert.exists() or not key.exists() or not state.exists() or state.read_text()!=signature
    if not changed:
        changed=subprocess.run(['openssl','x509','-checkend','604800','-noout','-in',str(cert)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10).returncode!=0
    if changed:
        import tempfile,secrets
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            temp=Path(temporary);extensions=temp/'extensions'
            extensions.write_text('subjectAltName='+','.join('IP:'+v for v in values)+'\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\n')
            command(['openssl','req','-new','-newkey','ec','-pkeyopt','ec_paramgen_curve:prime256v1','-nodes','-subj','/CN=ServiceReady','-keyout',str(temp/'key'),'-out',str(temp/'request')])
            command(['openssl','x509','-req','-in',str(temp/'request'),'-CA',str(ca_cert),'-CAkey',str(ca_key),'-set_serial','0x'+secrets.token_hex(16),'-days','90','-extfile',str(extensions),'-out',str(temp/'certificate')])
            (temp/'key').chmod(0o600);(temp/'certificate').chmod(0o644)
            (temp/'key').replace(key);(temp/'certificate').replace(cert)
    port=int(config.get('public_port',443));body_limit=int(config.get('update_upload_limit',64*1024**2))+16384
    text=MARKER+f'''user serviceready serviceready;
worker_processes 1;
pid /run/serviceready-nginx.pid;
error_log stderr warn;
events {{ worker_connections 64; }}
http {{
    access_log off;
    client_body_temp_path /tmp/serviceready;
    proxy_temp_path /tmp/serviceready;
    server {{
        listen {port} ssl;
        listen [::]:{port} ssl;
        ssl_certificate {cert};
        ssl_certificate_key {key};
        ssl_protocols TLSv1.2 TLSv1.3;
        client_max_body_size {body_limit};
        location / {{
            proxy_request_buffering off;
            proxy_buffering off;
            proxy_pass http://127.0.0.1:8080;
            proxy_set_header Host $http_host;
            proxy_set_header X-Forwarded-Proto https;
            proxy_set_header X-Forwarded-For $remote_addr;
        }}
    }}
}}
'''
    changed=changed or not proxy.exists() or proxy.read_text()!=text
    if changed:proxy.write_text(text);proxy.chmod(0o644)
    if changed and root==Path('/'):
        command(['nginx','-t','-c',str(proxy)])
        if changed and reload:command(['/etc/init.d/serviceready-proxy','reload'])
    state.write_text(signature)
    return origin(config,primary)
