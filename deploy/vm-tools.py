"""Trusted Rocky guest-tools updater. Never executes administrator-supplied commands."""
import hashlib,os,pathlib,platform,re,shutil,subprocess,tempfile
from urllib.request import urlopen

def output(args):return subprocess.check_output(args,text=True,stderr=subprocess.DEVNULL,timeout=15).strip()
def hypervisor():
    try:value=output(['/usr/bin/systemd-detect-virt','--vm'])
    except (OSError,subprocess.SubprocessError):value=''
    if value=='vmware':return 'vmware'
    if value=='oracle':return 'virtualbox'
    try:identity=(pathlib.Path('/sys/class/dmi/id/sys_vendor').read_text()+' '+pathlib.Path('/sys/class/dmi/id/product_name').read_text()).lower()
    except OSError:identity=''
    if 'vmware' in identity:return 'vmware'
    if 'virtualbox' in identity:return 'virtualbox'
    return 'unsupported'

def download(url,target,limit):
    digest=hashlib.sha256();total=0
    with urlopen(url,timeout=60) as response,open(target,'wb') as file:
        if not response.geturl().startswith('https://download.virtualbox.org/virtualbox/'):raise ValueError('Unexpected Oracle download destination.')
        while True:
            data=response.read(1024*1024)
            if not data:break
            total+=len(data)
            if total>limit:raise ValueError('Guest Additions download exceeds size limit.')
            file.write(data);digest.update(data)
    return digest.hexdigest()

def checksum(text,name):
    for line in text.splitlines():
        fields=line.split()
        if len(fields)==2 and fields[1].lstrip('*')==name and re.fullmatch('[a-fA-F0-9]{64}',fields[0]):return fields[0].lower()
    raise ValueError('Oracle checksum for this Guest Additions image is unavailable.')

def update(run,report):
    if not pathlib.Path('/etc/rocky-release').is_file():raise ValueError('Guest-tool updates currently require Rocky Linux.')
    provider=hypervisor()
    if provider=='vmware':
        report('Installing or updating VMware guest tools from host repositories')
        run(['/usr/bin/dnf','-y','install','open-vm-tools']);run(['/usr/bin/dnf','-y','upgrade','open-vm-tools'])
        run(['/usr/bin/systemctl','enable','--now','vmtoolsd']);run(['/usr/bin/systemctl','restart','vmtoolsd'])
        return 'VMware guest tools updated from host repositories. No reboot performed.'
    if provider!='virtualbox':raise ValueError('VMware or VirtualBox host not detected; guest-tool updates are unavailable.')
    control=shutil.which('VBoxControl')
    if not control:raise ValueError('Install initial VirtualBox Guest Additions from the hypervisor CD first; automatic updates require VBoxControl to identify the host version.')
    try:package=output(['/usr/bin/rpm','-qf','--qf','%{NAME}',control])
    except subprocess.SubprocessError:package=''
    if package:
        if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9+_.-]*',package):raise ValueError('Unexpected guest-tools package name.')
        report('Updating distribution-managed VirtualBox Guest Additions')
        run(['/usr/bin/dnf','-y','upgrade',package]);return 'Distribution-managed VirtualBox Guest Additions updated. A reboot may be needed; none performed.'
    host=output([control,'guestproperty','get','/VirtualBox/HostInfo/VBoxVer'])
    match=re.fullmatch(r'Value:\s*(\d+\.\d+\.\d+)',host)
    if not match:raise ValueError('VirtualBox host version unavailable. Enable guest properties and use a stable VirtualBox release.')
    version=match[1];installed=output([control,'--version']).split('r',1)[0].strip()
    if installed==version:return 'VirtualBox Guest Additions already match host '+version+'.'
    if platform.machine() not in ('x86_64','aarch64'):raise ValueError('Unsupported Guest Additions architecture.')
    report('Preparing build dependencies for the running kernel')
    run(['/usr/bin/dnf','-y','install','gcc','make','perl','elfutils-libelf-devel','kernel-devel-'+platform.release()])
    name='VBoxGuestAdditions_'+version+'.iso';base='https://download.virtualbox.org/virtualbox/'+version+'/'
    report('Downloading and verifying Oracle Guest Additions '+version)
    with tempfile.TemporaryDirectory(prefix='serviceready-vmtools-') as folder:
        root=pathlib.Path(folder);sums=root/'SHA256SUMS';image=root/name;mount=root/'media';mount.mkdir()
        download(base+'SHA256SUMS',sums,1024*1024);expected=checksum(sums.read_text(),name)
        if download(base+name,image,200*1024*1024)!=expected:raise ValueError('Guest Additions checksum mismatch; installer was not run.')
        run(['/usr/bin/mount','-o','loop,ro,nosuid,nodev,noexec',str(image),str(mount)])
        try:
            report('Installing verified VirtualBox Guest Additions; inspect /var/log/vboxadd-setup.log if kernel modules fail')
            run(['/bin/sh',str(mount/'VBoxLinuxAdditions.run'),'--nox11'])
        finally:run(['/usr/bin/umount',str(mount)])
    return 'VirtualBox Guest Additions '+version+' installed to match the host. A reboot may be needed; none performed.'
