"""Client for the root-owned Alpine account broker; never reads shadow files."""
import json
import socket

class LinuxAccounts:
    def __init__(self, path): self.path = path
    def call(self, action, username, password, new_password=None):
        request = dict(action=action,username=username,password=password)
        if new_password is not None: request['new_password']=new_password
        try:
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
                connection.settimeout(15)
                connection.connect(self.path)
                connection.sendall(json.dumps(request).encode()+b'\n')
                response = connection.makefile('rb').readline(8193)
            result=json.loads(response)
        except (OSError,ValueError): raise ValueError('System account service is unavailable.') from None
        if not result.get('ok'): raise ValueError(result.get('error','Account operation failed.'))
        return result.get('status',{}) if action=='maintenance-status' or action.startswith('terminal-') else True
