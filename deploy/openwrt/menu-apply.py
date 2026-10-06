#!/usr/bin/env python3
"""Fixed UCI operations for console setup; network backups allow console recovery."""
import ipaddress,json,os,pathlib,re,shutil,subprocess,sys,time
CONFIG=pathlib.Path('/etc/serviceready/config.json')
def run(args):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=30).strip()
def network(interface,method,address,gateway,dns):
    if not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,31}',interface) or method not in ('dhcp','static'):raise ValueError('Choose a valid logical interface and address method.')
    if run(['uci','get','network.'+interface])!='interface':raise ValueError('Logical interface not found.')
    values=[]
    if method=='static':
        cidr=ipaddress.IPv4Interface(address);gw=ipaddress.IPv4Address(gateway)
        if cidr.ip.is_loopback or cidr.ip.is_unspecified or gw.is_loopback:raise ValueError('Use a reachable management address and gateway.')
        names=[str(ipaddress.ip_address(v)) for v in dns.split()]
        if not names:raise ValueError('Provide at least one DNS server.')
        values=[('ipaddr',str(cidr.ip)),('netmask',str(cidr.netmask)),('gateway',str(gw)),('dns',' '.join(names))]
    backup=pathlib.Path('/etc/serviceready/network-backup-'+str(time.time_ns()));shutil.copyfile('/etc/config/network',backup);backup.chmod(0o600)
    try:
        run(['uci','set','network.'+interface+'.proto='+method])
        if method=='dhcp':
            for key in ('ipaddr','netmask','gateway','dns'):subprocess.run(['uci','-q','delete','network.'+interface+'.'+key],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for key,value in values:run(['uci','set','network.'+interface+'.'+key+'='+value])
        run(['uci','commit','network']);run(['/etc/init.d/network','reload'])
    except Exception:
        shutil.copyfile(backup,'/etc/config/network');subprocess.run(['uci','revert','network'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);subprocess.run(['/etc/init.d/network','reload'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);raise
    return 'Network settings applied. Previous configuration: '+str(backup)+'. Keep this console open and confirm access at the new address.'
def ntp(servers):
    names=servers.split()
    if not 1<=len(names)<=8 or any(not re.fullmatch('[A-Za-z0-9][A-Za-z0-9.:-]{0,252}',name) for name in names):raise ValueError('Enter 1–8 valid NTP hostnames or addresses.')
    backup=pathlib.Path('/etc/serviceready/system-backup-'+str(time.time_ns()));shutil.copyfile('/etc/config/system',backup);backup.chmod(0o600)
    try:
        run(['uci','set','system.ntp=timeserver']);subprocess.run(['uci','-q','delete','system.ntp.server'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for name in names:run(['uci','add_list','system.ntp.server='+name])
        run(['uci','set','system.ntp.enabled=1']);run(['uci','commit','system']);run(['/etc/init.d/sysntpd','restart'])
    except Exception:
        shutil.copyfile(backup,'/etc/config/system');subprocess.run(['uci','revert','system'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);subprocess.run(['/etc/init.d/sysntpd','restart'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);raise
    return 'NTP servers saved.'
def status():
    from voiceservices.network_address import Addresses,origin
    config=json.loads(CONFIG.read_text());_,address=Addresses().current();url=origin(config,address) if address else config['public_url']
    code=CONFIG.parent/'setup-token'
    return 'Portal: '+url+'\n'+('Ownership code: '+code.read_text().strip() if code.exists() else 'Administrator setup is complete.')+'\nTrust this VM’s CA certificate before entering credentials.'
def tools():
    values=[]
    for binary in ('vmware-toolbox-cmd','VBoxControl'):
        if shutil.which(binary):
            try:values.append(binary+': '+run([binary,'--version' if binary=='VBoxControl' else '-v']))
            except subprocess.SubprocessError:values.append(binary+': installed; runtime verification required')
    return '\n'.join(values) or 'No guest agent detected. Include the matching provider profile when building this image.'
if __name__=='__main__':
    if os.geteuid()!=0 or not pathlib.Path('/etc/openwrt_release').exists():raise SystemExit('Run on OpenWrt as root.')
    try:
        kind=sys.argv[1]
        print(status() if kind=='status' else tools() if kind=='tools' else ntp(sys.argv[2]) if kind=='ntp' else network(*sys.argv[2:]) if kind=='network' else 'Unknown setup area.')
    except (ValueError,OSError,subprocess.SubprocessError) as error:raise SystemExit(str(error))
