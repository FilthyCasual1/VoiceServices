"""Offline portal, distribution and detected VM provider marks."""
from functools import lru_cache
from pathlib import Path
import subprocess

@lru_cache(maxsize=1)
def provider():
    try:value=subprocess.check_output(['systemd-detect-virt','--vm'],text=True,stderr=subprocess.DEVNULL,timeout=2).strip()
    except (OSError,subprocess.SubprocessError):value=''
    if value=='vmware':return 'vmware','VMware'
    if value=='oracle':return 'virtualbox','VirtualBox'
    try:identity=(Path('/sys/class/dmi/id/sys_vendor').read_text()+' '+Path('/sys/class/dmi/id/product_name').read_text()).lower()
    except OSError:identity=''
    if 'vmware' in identity:return 'vmware','VMware'
    if 'virtualbox' in identity:return 'virtualbox','VirtualBox'
    return None,'Host'

def marks():
    identifier,label=provider()
    result='<div class="host-brand-marks"><img src="/host/distro-logo" alt="Host distribution logo" title="Host operating system">'
    if identifier:result+='<img class="provider-mark" src="/static/provider-'+identifier+'.svg" alt="'+label+'" title="'+label+'">'
    return result+'</div>'
