"""Package a prebuilt OpenWrt raw disk as a portable OVF/VMDK OVA."""
import argparse,gzip,hashlib,json,pathlib,shutil,subprocess,tarfile,tempfile
from xml.etree import ElementTree as ET
OVF='http://schemas.dmtf.org/ovf/envelope/1';RASD='http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData';VSSD='http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData'
for prefix,namespace in [('ovf',OVF),('rasd',RASD),('vssd',VSSD)]:ET.register_namespace(prefix,namespace)
def descriptor(name,capacity,disk_size,memory,cpus):
    root=ET.Element('{'+OVF+'}Envelope')
    def child(parent,tag,text=None,attrs=None,ns=OVF):
        node=ET.SubElement(parent,'{'+ns+'}'+tag,attrs or {})
        if text is not None:node.text=str(text)
        return node
    refs=child(root,'References');child(refs,'File',attrs={'{'+OVF+'}id':'disk','{'+OVF+'}href':'insap.vmdk','{'+OVF+'}size':str(disk_size)})
    disks=child(root,'DiskSection');child(disks,'Info','Appliance boot disk');child(disks,'Disk',attrs={'{'+OVF+'}diskId':'boot','{'+OVF+'}fileRef':'disk','{'+OVF+'}capacity':str(capacity),'{'+OVF+'}capacityAllocationUnits':'byte','{'+OVF+'}format':'http://www.vmware.com/interfaces/specifications/vmdk.html#streamOptimized'})
    network=child(root,'NetworkSection');child(network,'Info','DHCP management network');net=child(network,'Network',attrs={'{'+OVF+'}name':'Management'});child(net,'Description','Connect to an existing DHCP management network')
    vm=child(root,'VirtualSystem',attrs={'{'+OVF+'}id':'INSAP'});child(vm,'Info',name);child(vm,'Name',name)
    os_section=child(vm,'OperatingSystemSection',attrs={'{'+OVF+'}id':'101'});child(os_section,'Info','OpenWrt x86-64 Linux')
    hardware=child(vm,'VirtualHardwareSection');child(hardware,'Info','Small INSAP appliance');system=child(hardware,'System');child(system,'VirtualSystemIdentifier',name,ns=VSSD);child(system,'VirtualSystemType','vmx-13',ns=VSSD)
    def item(id,type,name,quantity=None,parent=None,subtype=None,host=None,address=None):
        node=child(hardware,'Item')
        for tag,value in [('InstanceID',id),('ResourceType',type),('ElementName',name),('VirtualQuantity',quantity),('Parent',parent),('ResourceSubType',subtype),('HostResource',host),('AddressOnParent',address)]:
            if value is not None:child(node,tag,value,ns=RASD)
        return node
    item(1,3,'Virtual CPUs',cpus);ram=item(2,4,'Memory',memory);child(ram,'AllocationUnits','byte * 2^20',ns=RASD)
    item(3,5,'IDE controller');item(4,17,'INSAP boot disk',parent=3,host='ovf:/disk/boot',address=0)
    nic=item(5,10,'Management adapter',subtype='E1000',address=0);child(nic,'Connection','Management',ns=RASD);child(nic,'AutomaticAllocation','true',ns=RASD)
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)
def build(source,output,name='ServiceReady INSAP',memory=256,cpus=1):
    if not 64<=memory<=65536 or not 1<=cpus<=32:raise ValueError('Invalid VM resources.')
    if output.exists():raise ValueError('Choose a new OVA output file.')
    if not shutil.which('qemu-img'):raise ValueError('Install qemu-img on the image-building machine, not inside the appliance.')
    with tempfile.TemporaryDirectory() as temporary:
        folder=pathlib.Path(temporary);raw=source
        if source.suffix=='.gz':
            raw=folder/'disk.img'
            with gzip.open(source,'rb') as incoming,raw.open('wb') as target:shutil.copyfileobj(incoming,target)
        info=json.loads(subprocess.check_output(['qemu-img','info','--output=json',str(raw)],text=True))
        if info['format']!='raw':raise ValueError('Provide a combined OpenWrt raw .img or .img.gz, not a sysupgrade tar.')
        disk=folder/'insap.vmdk';subprocess.run(['qemu-img','convert','-f','raw','-O','vmdk','-o','subformat=streamOptimized',str(raw),str(disk)],check=True)
        ovf=folder/'insap.ovf';ovf.write_bytes(descriptor(name,info['virtual-size'],disk.stat().st_size,memory,cpus))
        manifest=folder/'insap.mf'
        def digest(path):
            value=hashlib.sha256()
            with path.open('rb') as source:
                for chunk in iter(lambda:source.read(1024*1024),b''):value.update(chunk)
            return value.hexdigest()
        manifest.write_text(''.join('SHA256 ('+path.name+') = '+digest(path)+'\n' for path in (ovf,disk)))
        output.parent.mkdir(parents=True,exist_ok=True)
        with tarfile.open(output,'w',format=tarfile.USTAR_FORMAT) as archive:
            for path in (ovf,manifest,disk):archive.add(path,arcname=path.name)
    return output
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('disk',type=pathlib.Path);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--name',default='ServiceReady INSAP');p.add_argument('--memory',type=int,default=256);p.add_argument('--cpus',type=int,default=1);a=p.parse_args();print(build(a.disk,a.output,a.name,a.memory,a.cpus))
