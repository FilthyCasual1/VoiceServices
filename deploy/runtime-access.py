#!/usr/bin/env python3
"""Keep the root-owned runtime readable by its service group, never writable."""
import grp,json,os,pathlib,pwd,re,stat,subprocess

def normalise_runtime(root=pathlib.Path('/opt/serviceready/venv'),gid=None,owner_uid=0):
    gid=grp.getgrnam('serviceready').gr_gid if gid is None else gid
    if root.is_symlink() or not root.is_dir():raise ValueError('Runtime must be a real directory.')
    for directory,dirs,files in os.walk(root,followlinks=False):
        for path in [pathlib.Path(directory)]+[pathlib.Path(directory)/name for name in files]:
            if path.is_symlink():continue # Never change the system interpreter or external symlink targets.
            metadata=path.stat()
            if not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):raise ValueError('Unexpected special file in runtime.')
            os.chown(path,owner_uid,gid)
            mode=stat.S_IMODE(metadata.st_mode)&~0o022
            mode|=0o040
            if path.is_dir() or mode&0o111:mode|=0o010
            os.chmod(path,mode)

def record_build(root=pathlib.Path('/opt/serviceready/venv'),source=pathlib.Path('/opt/serviceready/source')):
    if not (source/'.git').exists():return
    commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if not re.fullmatch('[a-f0-9]{40}',commit):raise ValueError('Invalid GitHub checkout revision.')
    package=pathlib.Path(subprocess.check_output([str(root/'bin/python'),'-I','-c',"import importlib.util,pathlib; print(pathlib.Path(importlib.util.find_spec('voiceservices').origin).parent)"],text=True).strip())
    if not package.resolve().is_relative_to(root.resolve()):raise ValueError('Build metadata must be inside the installed runtime.')
    metadata=package/'build_info.json';metadata.write_text(json.dumps({'github_commit':commit})+'\n');os.chmod(metadata,0o640)

def verify_runtime(root=pathlib.Path('/opt/serviceready/venv')):
    account=pwd.getpwnam('serviceready')
    subprocess.run([str(root/'bin/python'),'-I','-c','from voiceservices.server import main; import waitress, pyotp, segno, pyftpdlib, aiosmtpd'],check=True,timeout=30,cwd='/var/lib/serviceready',user=account.pw_uid,group=account.pw_gid,extra_groups=[account.pw_gid])

def normalise_addons(config,uid=None,gid=None):
    account=pwd.getpwnam('serviceready') if uid is None or gid is None else None
    uid=account.pw_uid if uid is None else uid;gid=account.pw_gid if gid is None else gid
    root=pathlib.Path(config.get('addon_directory',str(pathlib.Path(config['database']).parent/'addons')))
    if root.is_symlink():raise ValueError('Addon directory must not be a symlink.')
    if not root.exists():return
    for directory,dirs,files in os.walk(root,followlinks=False):
        for path in [pathlib.Path(directory)]+[pathlib.Path(directory)/name for name in files]:
            if path.is_symlink():continue
            os.chown(path,uid,gid);os.chmod(path,0o750 if path.is_dir() else 0o640)

if __name__=='__main__':
    if os.geteuid()!=0:raise SystemExit('Run this helper as root.')
    record_build();normalise_runtime();verify_runtime()
