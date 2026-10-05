"""Read-only SNMPv2c monitoring and bounded trap reception."""
import html,ipaddress,json,secrets,socket,time
E=lambda v:html.escape(str(v),quote=True)
DEFAULT={'enabled':False,'host':'127.0.0.1','port':1162,'allowed':'127.0.0.1/32','community':'','interval':60,'devices':[]}
def tlv(tag,data):
    n=len(data);length=bytes([n]) if n<128 else bytes([128+(n.bit_length()+7)//8])+n.to_bytes((n.bit_length()+7)//8,'big')
    return bytes([tag])+length+data
def integer(n):
    return tlv(2,n.to_bytes(max(1,(n.bit_length()+8)//8),'big',signed=True))
def base128(n):
    out=[n&127];n>>=7
    while n: out.insert(0,128|(n&127));n>>=7
    return bytes(out)
def oid_bytes(value):
    parts=[int(x) for x in value.strip('.').split('.')]
    if len(parts)<2 or not 0<=parts[0]<=2 or parts[1]<0 or (parts[0]<2 and parts[1]>39) or any(not 0<=n<=2**32-1 for n in parts): raise ValueError('Invalid numeric OID.')
    return b''.join(base128(n) for n in [parts[0]*40+parts[1],*parts[2:]])
def oid_text(raw):
    parts=[];n=0
    for byte in raw:
        n=n*128+(byte&127)
        if n>2**35: raise ValueError('OID too large')
        if byte<128: parts.append(n);n=0
    if not parts or raw[-1]&128: raise ValueError('Invalid OID')
    first=parts.pop(0);a=min(first//40,2)
    return '.'.join(map(str,[a,first-40*a,*parts]))
def items(raw):
    out=[];offset=0
    while offset<len(raw):
        if len(out)>256 or offset+2>len(raw): raise ValueError('Invalid BER')
        tag,n=raw[offset:offset+2];offset+=2
        if n&128:
            count=n&127
            if not 1<=count<=4 or offset+count>len(raw): raise ValueError('Invalid BER length')
            n=int.from_bytes(raw[offset:offset+count],'big');offset+=count
        if offset+n>len(raw): raise ValueError('Truncated BER')
        out.append((tag,raw[offset:offset+n]));offset+=n
    return out
def number(item):
    if item[0]!=2 or not 1<=len(item[1])<=5: raise ValueError('Invalid integer')
    return int.from_bytes(item[1],'big',signed=True)
def message(community,tag,request,bindings,error=0,index=0):
    pairs=b''.join(tlv(48,tlv(6,oid_bytes(oid))+value) for oid,value in bindings)
    return tlv(48,integer(1)+tlv(4,community.encode())+tlv(tag,integer(request)+integer(error)+integer(index)+tlv(48,pairs)))
def decode(raw):
    outer=items(raw)
    if len(outer)!=1 or outer[0][0]!=48: raise ValueError('Invalid SNMP message')
    envelope=items(outer[0][1])
    if len(envelope)!=3 or number(envelope[0])!=1 or envelope[1][0]!=4: raise ValueError('Only SNMPv2c is supported')
    tag,pdu=envelope[2];fields=items(pdu)
    if len(fields)!=4 or fields[3][0]!=48: raise ValueError('Invalid PDU')
    request,error,index=map(number,fields[:3]);bindings=[]
    for pairtag,pair in items(fields[3][1]):
        values=items(pair)
        if pairtag!=48 or len(values)!=2 or values[0][0]!=6: raise ValueError('Invalid binding')
        oid=oid_text(values[0][1]);vtag,value=values[1]
        text=oid_text(value) if vtag==6 else str(int.from_bytes(value,'big',signed=vtag==2)) if vtag in (2,65,66,67,70) else value.decode('utf-8','replace') if vtag==4 else 'Unavailable' if vtag in (128,129,130) else value.hex()
        bindings.append((oid,text[:1000],tlv(vtag,value)))
    return envelope[1][1],tag,request,error,index,bindings

def settings(app):
    with app.store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS addon_status(id TEXT PRIMARY KEY,status TEXT,at INTEGER)')
        db.execute('CREATE TABLE IF NOT EXISTS snmp_results(name TEXT PRIMARY KEY,status TEXT,values_json TEXT,at INTEGER)')
        db.execute('CREATE TABLE IF NOT EXISTS snmp_traps(id INTEGER PRIMARY KEY,source TEXT,bindings TEXT,at INTEGER)')
        row=db.execute("SELECT settings FROM addons WHERE id='snmp'").fetchone()
    return dict(DEFAULT,**(json.loads(row[0]) if row else {}))
def admin_change(app,data,services):
    s=settings(app)
    if data.get('action')=='device':
        name=data.get('name','').strip()[:80];host=data.get('address','').strip();ipaddress.ip_address(host)
        port=int(data.get('device_port','161'));community=data.get('device_community','');oids=data.get('oids','').split()
        if not name or not community or len(community)>128 or not 1<=port<=65535 or not 1<=len(oids)<=32: raise ValueError('Enter a name, IP, community, port and 1–32 OIDs.')
        for oid in oids: oid_bytes(oid)
        devices=[d for d in s['devices'] if d['name']!=name]
        if len(devices)>=32: raise ValueError('Maximum 32 devices.')
        s['devices']=devices+[dict(name=name,host=host,port=port,community=community,oids=oids)]
    elif data.get('action')=='remove':
        s['devices']=[d for d in s['devices'] if d['name']!=data.get('name')]
        with app.store.connect() as db: db.execute('DELETE FROM snmp_results WHERE name=?',(data.get('name'),))
    else:
        s['enabled']=data.get('enabled')=='yes';s['host']=data.get('host','127.0.0.1');ipaddress.ip_address(s['host'])
        s['port']=int(data.get('port','1162'));s['interval']=int(data.get('interval','60'));s['allowed']=data.get('allowed','')
        networks=[ipaddress.ip_network(x.strip(),strict=False) for x in s['allowed'].split(',')]
        if not networks or not 1024<=s['port']<=65535 or not 15<=s['interval']<=3600: raise ValueError('Use port 1024–65535 and interval 15–3600 seconds.')
        if data.get('community'):
            if len(data['community'])>128: raise ValueError('Community must be at most 128 characters.')
            s['community']=data['community']
        if s['enabled'] and not s['community']: raise ValueError('Set the trap community before enabling.')
    with app.store.connect() as db: db.execute("INSERT OR REPLACE INTO addons VALUES('snmp',?)",(json.dumps(s),))
    return 'SNMP settings saved.'
def admin_render(app,user,services):
    from voiceservices import regional
    s=settings(app);csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
    with app.store.connect() as db:
        results={r['name']:r for r in db.execute('SELECT * FROM snmp_results')};traps=list(db.execute('SELECT * FROM snmp_traps ORDER BY id DESC LIMIT 100'))
        state=db.execute("SELECT status,at FROM addon_status WHERE id='snmp'").fetchone()
    status=state['status'] if state and state['at']>time.time()-10 else 'Worker unavailable'
    text='<p class="notice">'+E(status)+'</p><p>Read-only SNMPv2c polling and traps. Communities travel in clear text; use a trusted management network. SNMPv1 and v3 are not supported.</p><details class="settings-section"><summary>Polling and trap receiver settings</summary><form method="post">'+csrf
    for key,label in [('host','Trap listen IP'),('port','Trap UDP port'),('allowed','Trusted trap source CIDRs'),('interval','Polling interval (seconds)')]: text+='<label>'+label+'</label><input name="'+key+'" value="'+E(s[key])+'">'
    text+='<label>Trap community (blank keeps existing)</label><input type="password" name="community" autocomplete="new-password"><label><input type="checkbox" name="enabled" value="yes"'+(' checked' if s['enabled'] else '')+'> Enable polling and traps</label><button>Save settings</button></form></details><details class="settings-section"><summary>Add or replace monitored device</summary><form method="post">'+csrf+'<input type="hidden" name="action" value="device">'
    for key,label,value in [('name','Name',''),('address','Device IP',''),('device_port','UDP port','161'),('device_community','Read-only community',''),('oids','Numeric OIDs (space-separated)','1.3.6.1.2.1.1.1.0 1.3.6.1.2.1.1.3.0 1.3.6.1.2.1.1.5.0')]: text+='<label>'+label+'</label><input name="'+key+'" type="'+('password' if key=='device_community' else 'text')+'" value="'+value+'" required>'
    text+='<button>Save device</button></form></details><h3>Monitored devices</h3>'
    for d in s['devices']:
        r=results.get(d['name']);text+='<div class="panel"><strong>'+E(d['name'])+'</strong> — '+E(d['host'])+'<p>'+E(r['status'] if r else 'Awaiting poll')+'</p>'
        if r: text+='<p>'+E(regional.format_timestamp(app,r['at']))+'</p><pre>'+E('\n'.join(k+' = '+v for k,v in json.loads(r['values_json'])))+'</pre>'
        text+='<form method="post">'+csrf+'<input type="hidden" name="name" value="'+E(d['name'])+'"><button name="action" value="remove">Remove device</button></form></div>'
    text+='<h3>Recent traps (latest 100)</h3>'
    for r in traps: text+='<div class="panel"><strong>'+E(r['source'])+'</strong> — '+E(regional.format_timestamp(app,r['at']))+'<pre>'+E('\n'.join(k+' = '+v for k,v in json.loads(r['bindings'])))+'</pre></div>'
    return text+('' if traps else '<p>No traps received.</p>')
def poll(device):
    request=secrets.randbelow(2**30);packet=message(device['community'],160,request,[(o,tlv(5,b'')) for o in device['oids']])
    family=socket.AF_INET6 if ':' in device['host'] else socket.AF_INET
    with socket.socket(family,socket.SOCK_DGRAM) as client:
        client.settimeout(2);client.connect((device['host'],device['port']));client.send(packet)
        community,tag,rid,error,index,bindings=decode(client.recv(65535))
    if community!=device['community'].encode() or tag!=162 or rid!=request: raise ValueError('Unexpected SNMP response')
    if error: raise ValueError('Agent error '+str(error)+' at binding '+str(index))
    if [b[0] for b in bindings]!=device['oids']: raise ValueError('Unexpected response OIDs')
    return [(o,v) for o,v,_ in bindings]
def receive(app,s,raw,peer):
    if not any(ipaddress.ip_address(peer[0]) in ipaddress.ip_network(x.strip(),strict=False) for x in s['allowed'].split(',')): return None
    community,tag,request,error,index,bindings=decode(raw)
    if not secrets.compare_digest(community,s['community'].encode()) or tag not in (166,167) or error or index: return None
    if len(bindings)<2 or [b[0] for b in bindings[:2]]!=['1.3.6.1.2.1.1.3.0','1.3.6.1.6.3.1.1.4.1.0']: raise ValueError('Missing trap identity bindings')
    with app.store.connect() as db:
        # Cap disk growth even if a trusted sender floods the receiver.
        recent=db.execute('SELECT COUNT(*) FROM snmp_traps WHERE at>=?',(int(time.time())-1,)).fetchone()[0]
        if recent>=20: return None
        db.execute('INSERT INTO snmp_traps(source,bindings,at) VALUES(?,?,?)',(peer[0],json.dumps([(o,v) for o,v,_ in bindings]),int(time.time())))
        db.execute('DELETE FROM snmp_traps WHERE id NOT IN (SELECT id FROM snmp_traps ORDER BY id DESC LIMIT 1000)')
    return message(s['community'],162,request,[(o,v) for o,_,v in bindings]) if tag==166 else None
def worker_main():
    import argparse,concurrent.futures
    from voiceservices.web import App
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);args=parser.parse_args()
    with open(args.config) as f: app=App(json.load(f))
    sock=None;previous=None;next_poll=0;futures={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        try:
            while app.modules.installed('snmp'):
                s=settings(app)
                if s!=previous:
                    if sock: sock.close();sock=None
                    previous=s;next_poll=0
                    if s['enabled']:
                        sock=socket.socket(socket.AF_INET6 if ':' in s['host'] else socket.AF_INET,socket.SOCK_DGRAM);sock.bind((s['host'],s['port']));sock.settimeout(.2)
                if s['enabled'] and time.time()>=next_poll and not futures:
                    futures={pool.submit(poll,d):d['name'] for d in s['devices']};next_poll=time.time()+s['interval']
                for future in list(futures):
                    if not future.done(): continue
                    name=futures.pop(future)
                    try: values=future.result();status='Responding'
                    except (OSError,ValueError): values=[];status='Unavailable or invalid response'
                    if s['enabled'] and name in {d['name'] for d in s['devices']}:
                        with app.store.connect() as db: db.execute('INSERT OR REPLACE INTO snmp_results VALUES(?,?,?,?)',(name,status,json.dumps(values),int(time.time())))
                if sock:
                    try:
                        raw,peer=sock.recvfrom(65535);reply=receive(app,s,raw,peer)
                        if reply: sock.sendto(reply,peer)
                    except (socket.timeout,ValueError,IndexError): pass
                else: time.sleep(.2)
                with app.store.connect() as db: db.execute("INSERT OR REPLACE INTO addon_status VALUES('snmp',?,?)",('Running; '+str(len(s['devices']))+' monitored devices' if sock else 'Disabled',int(time.time())))
        finally:
            if sock: sock.close()
