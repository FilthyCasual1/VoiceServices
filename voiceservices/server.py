"""Installed WSGI service entry point (Waitress is supplied by the installer)."""
import argparse
import json
from .web import App

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='/etc/serviceready/config.json')
    args = parser.parse_args()
    with open(args.config) as source: config = json.load(source)
    if config.get("data_mount"):
        import tempfile
        tempfile.tempdir=config["data_mount"]+"/tmp"
    from waitress import serve
    proxy={}
    if config.get('trusted_proxy'):
        proxy=dict(trusted_proxy=config['trusted_proxy'],trusted_proxy_count=1,trusted_proxy_headers={'x-forwarded-for','x-forwarded-proto'})
    serve(App(config), **proxy, host=config.get('listen_host','0.0.0.0'),
          port=int(config.get('listen_port',8080)), threads=4,
          max_request_body_size=int(config.get('update_upload_limit',8*1024**3))+16384,
          inbuf_overflow=1024**2)

if __name__ == '__main__': main()
