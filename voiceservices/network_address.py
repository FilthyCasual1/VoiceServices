"""Read current Linux interface addresses without trusting browser Host headers."""
import ipaddress,json,subprocess,time
from urllib.parse import urlsplit

class Addresses:
    def __init__(self):self.expires=0;self.values=[];self.primary=None
    def current(self):
        if time.monotonic()<self.expires:return self.values,self.primary
        values=[];primary=None
        try:
            rows=json.loads(subprocess.check_output(['ip','-j','address','show','up'],timeout=2,text=True))
            for row in rows:
                for entry in row.get('addr_info',[]):
                    address=ipaddress.ip_address(entry['local'])
                    if entry.get('scope')=='global' and not address.is_loopback and not address.is_link_local and not address.is_unspecified:
                        values.append(str(address))
            values=sorted(set(values),key=lambda value:(ipaddress.ip_address(value).version,value))
            try:
                routes=json.loads(subprocess.check_output(['ip','-j','route','get','1.1.1.1'],timeout=2,text=True))
                primary=next((r.get('prefsrc') for r in routes if r.get('prefsrc') in values),None)
            except (OSError,ValueError,subprocess.SubprocessError):pass
            primary=primary or (values[0] if values else None)
        except (OSError,ValueError,KeyError,subprocess.SubprocessError):pass
        self.values,self.primary=values,primary;self.expires=time.monotonic()+5
        return values,primary

def origin(config,address):
    scheme=urlsplit(config.get('public_url','http://localhost:8080')).scheme
    port=int(config.get('public_port',443 if scheme=='https' else config.get('listen_port',8080)))
    host='['+address+']' if ':' in address else address
    return scheme+'://'+host+(':'+str(port) if port!=(443 if scheme=='https' else 80) else '')

def caddy_config(addresses,primary,port):
    names=', '.join('https://'+('['+a+']' if ':' in a else a) for a in addresses)
    return '# ServiceReady managed address configuration\n'+names+' {\n    tls internal\n    reverse_proxy 127.0.0.1:'+str(int(port))+'\n}\n'
