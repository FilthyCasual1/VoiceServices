"""iPXE profiles: ISO boot and interactive Clonezilla restoration."""
import ipaddress
import json
import re
from .library import E

def url(value):
    from urllib.parse import urlsplit
    parsed=urlsplit(value)
    if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or parsed.password or re.search(r'[\s\"\x27;&$<>\\]',value): raise ValueError('Boot URLs must be HTTP(S), without credentials, whitespace or command characters.')
    return value

class PXE:
    def __init__(self,app):
        self.app=app
        with app.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS pxe_profiles(id INTEGER PRIMARY KEY,title TEXT,kind TEXT,settings TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS pxe_settings(id INTEGER PRIMARY KEY,settings TEXT)')
    def profiles(self):
        with self.app.store.connect() as db: return db.execute('SELECT * FROM pxe_profiles ORDER BY id').fetchall()
    def settings(self):
        with self.app.store.connect() as db:
            row=db.execute('SELECT settings FROM pxe_settings WHERE id=1').fetchone()
            return json.loads(row[0]) if row else {'enabled':False,'subnet':'','address':''}
    def change(self,data):
        action=data.get('action','')
        if action=='network':
            enabled=data.get('enabled')=='yes'
            subnet=data.get('subnet','');address=data.get('address','')
            if subnet or enabled:
                network=ipaddress.IPv4Network(subnet,strict=True);ip=ipaddress.IPv4Address(address)
                if ip not in network or ip in (network.network_address,network.broadcast_address): raise ValueError('Boot server address must be a host on the selected IPv4 subnet.')
                if network.prefixlen<16 or network.prefixlen>30: raise ValueError('Use a /16 to /30 testbed subnet.')
                if enabled:
                    for name in ('ipxe.efi','undionly.kpxe'):
                        if not (self.app.boot_files.root/name).is_file(): raise ValueError('Upload ipxe.efi and undionly.kpxe before enabling PXE.')
            with self.app.store.connect() as db: db.execute('INSERT OR REPLACE INTO pxe_settings VALUES(1,?)',(json.dumps(dict(enabled=enabled,subnet=subnet,address=address)),))
        elif action=='delete':
            with self.app.store.connect() as db: db.execute('DELETE FROM pxe_profiles WHERE id=?',(int(data.get('profile','')),))
        elif action=='profile':
            title=data.get('title','').strip();kind=data.get('kind','')
            if not re.fullmatch('[A-Za-z0-9 ._()-]{1,80}',title): raise ValueError('Use a simple profile title (letters, digits, spaces and punctuation).')
            if kind=='iso': settings={'iso':url(data.get('iso',''))}
            elif kind=='restore':
                settings={key:url(data.get(key,'')) for key in ('kernel','initrd','squashfs')}
                repository=data.get('repository','')
                if repository and not re.fullmatch(r'nfs://[A-Za-z0-9.-]+/[A-Za-z0-9_./-]+',repository): raise ValueError('Use an NFS repository URL such as nfs://server/images, or leave blank for manual repository selection.')
                settings['repository']=repository
            else: raise ValueError('Unknown boot profile type.')
            with self.app.store.connect() as db: db.execute('INSERT INTO pxe_profiles(title,kind,settings) VALUES(?,?,?)',(title,kind,json.dumps(settings)))
        else: raise ValueError('Unknown PXE action.')
    def script(self):
        lines=['#!ipxe','menu ServiceReady Network Deployment','item local Continue local boot']
        profiles=self.profiles()
        lines += ['item profile'+str(row['id'])+' '+row['title'] for row in profiles]
        lines += ['choose --default local --timeout 10000 selected || goto local','goto ${selected}',':local','exit']
        for row in profiles:
            settings=json.loads(row['settings']);lines.append(':profile'+str(row['id']))
            if row['kind']=='iso': lines.append('sanboot --no-describe '+settings['iso']+' || goto failed')
            else:
                args='boot=live union=overlay username=user config components quiet noswap ip=dhcp net.ifnames=0 fetch='+settings['squashfs']+' ocs_live_batch=no ocs_live_run="ocs-sr -l en_US.UTF-8 -c -p choose restoredisk ask_user ask_user"'
                if settings['repository']: args+=' ocs_repository="'+settings['repository']+'"'
                lines += ['kernel '+settings['kernel']+' '+args+' || goto failed','initrd '+settings['initrd']+' || goto failed','boot || goto failed']
            lines += ['goto local']
        return '\n'.join(lines+[':failed','echo Boot failed. Check image and firmware compatibility.','prompt Press any key to return','chain '+url(self.app.base+'/pxe/boot.ipxe')])+'\n'
    def render(self,user):
        csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
        content='<h2>PXE and image restoration</h2><p class="notice">Boot menu: <code>'+E(self.app.base+'/pxe/boot.ipxe')+'</code>. ISO compatibility depends on the image and firmware. Clonezilla restoration prompts for the image and target disk on the booted machine.</p>'
        settings=self.settings()
        content+='<h2>PXE network service</h2><div class="panel"><p>Optional proxy-DHCP and TFTP use your existing DHCP server. Enable only on the selected deployment subnet. Upload official ipxe.efi and undionly.kpxe bootloaders first.</p><form method="post">'+csrf+'<input name="action" type="hidden" value="network"><label>IPv4 subnet (CIDR)</label><input name="subnet" value="'+E(settings['subnet'])+'"><label>Boot server IPv4 address</label><input name="address" value="'+E(settings['address'])+'"><label>Proxy-DHCP / TFTP</label><select name="enabled"><option value="no">Disabled</option><option value="yes"'+(' selected' if settings['enabled'] else '')+'>Enabled</option></select><br><button>Save network settings</button></form></div>'
        content+='<h2>Boot profiles</h2><table><tr><th>Name</th><th>Mode</th><th>Action</th></tr>'
        for row in self.profiles(): content+='<tr><td>'+E(row['title'])+'</td><td>'+E(row['kind'])+'</td><td><form method="post">'+csrf+'<input type="hidden" name="profile" value="'+str(row['id'])+'"><button name="action" value="delete">Remove profile</button></form></td></tr>'
        content+='</table><h2>Add boot profile</h2><div class="panel"><form method="post">'+csrf+'<input type="hidden" name="action" value="profile"><label>Title</label><input name="title" required><label>Mode</label><select name="kind"><option value="iso">ISO boot</option><option value="restore">Clonezilla image restoration</option></select>'
        for key,label in [('iso','ISO URL (ISO mode)'),('kernel','Clonezilla vmlinuz URL (restore mode)'),('initrd','Clonezilla initrd.img URL'),('squashfs','Clonezilla filesystem.squashfs URL'),('repository','NFS image repository URL (optional)')]: content+='<label>'+label+'</label><input name="'+key+'">'
        content+='<br><button>Add profile</button></form></div><h2>Upload boot assets</h2><div class="panel"><form action="/admin/pxe/upload" method="post" enctype="multipart/form-data">'+csrf+'<label>File</label><input type="file" name="file" required><br><button>Upload asset</button></form></div><table><tr><th>Filename</th><th>HTTP URL</th><th>SHA-256</th></tr>'
        for row in self.app.boot_files.files(): content+='<tr><td>'+E(row['name'])+'</td><td><code>'+E(self.app.base+'/pxe/files/'+row['name'])+'</code></td><td><code>'+E(row['sha256'])+'</code></td></tr>'
        return content+'</table>'
