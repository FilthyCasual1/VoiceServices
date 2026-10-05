"""Installed WSGI service entry point (Waitress is supplied by the installer)."""
import argparse
import json
from .web import App

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='/etc/serviceready/config.json')
    args = parser.parse_args()
    with open(args.config) as source: config = json.load(source)
    from waitress import serve
    serve(App(config), host=config.get('listen_host','0.0.0.0'),
          port=int(config.get('listen_port',8080)), threads=4)

if __name__ == '__main__': main()
