import argparse
import getpass
import json
from wsgiref.simple_server import make_server, WSGIRequestHandler
from .web import App


class PrivateRequestHandler(WSGIRequestHandler):
    def log_message(self, fmt, *args):
        # Phone service URLs carry development bearer tokens. Never log request targets.
        pass


def main():
    parser = argparse.ArgumentParser(description='VoiceServices portal')
    parser.add_argument('--config', default='config.json')
    sub = parser.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve')
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=8080)
    create = sub.add_parser('create-user')
    create.add_argument('username')
    create.add_argument('--admin', action='store_true')
    args = parser.parse_args()
    with open(args.config) as f: app = App(json.load(f))
    if args.command == 'create-user':
        password = getpass.getpass('Password (12+ characters): ')
        if password != getpass.getpass('Confirm password: '): parser.error('Passwords differ.')
        app.store.create_user(args.username, password, 'admin' if args.admin else 'user')
        print('User created.')
    else:
        print(f'VoiceServices development server: http://{args.host}:{args.port}')
        with make_server(args.host,args.port,app,handler_class=PrivateRequestHandler) as server:
            server.serve_forever()


if __name__ == '__main__': main()
