"""Build a small, architecture-independent OpenWrt runtime without target-side pip."""
import argparse,hashlib,json,pathlib,shutil,subprocess,sys,tarfile,tempfile,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
DEPENDENCIES=('pyotp==2.9.0','segno==1.6.6','waitress==3.0.2')
def build(output,wheels):
    sys.path.insert(0,str(ROOT))
    from voiceservices.version import __version__
    commit=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    dirty=bool(subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain'],text=True).strip())
    with tempfile.TemporaryDirectory() as temporary:
        staging=pathlib.Path(temporary)/'serviceready-openwrt';app=staging/'app';app.mkdir(parents=True)
        shutil.copytree(ROOT/'voiceservices',app/'voiceservices',ignore=shutil.ignore_patterns('__pycache__','*.pyc','build_info.json'))
        hashes={}
        for dependency in DEPENDENCIES:
            name,version=dependency.split('==');matches=list(wheels.glob(name+'-'+version+'-*-none-any.whl'))
            if len(matches)!=1:raise ValueError('Provide exactly one pure Python wheel for '+dependency)
            wheel=matches[0];hashes[wheel.name]=hashlib.sha256(wheel.read_bytes()).hexdigest()
            with zipfile.ZipFile(wheel) as archive:
                for item in archive.infolist():
                    path=pathlib.PurePosixPath(item.filename)
                    if path.is_absolute() or '..' in path.parts or '.data' in path.parts:raise ValueError('Unsafe wheel member')
                    if item.is_dir():continue
                    target=app.joinpath(*path.parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(item))
        # A dirty build must not masquerade as an exact installed commit.
        revision='' if dirty else commit
        (app/'voiceservices/build_info.json').write_text(json.dumps({'github_commit':revision})+'\n')
        shutil.copytree(ROOT/'deploy/openwrt',staging/'deploy/openwrt',ignore=shutil.ignore_patterns('__pycache__','*.pyc','sdk'))
        shutil.copyfile(ROOT/'deploy/account-broker.py',staging/'deploy/account-broker.py')
        shutil.copyfile(ROOT/'install-openwrt.sh',staging/'install-openwrt.sh')
        shutil.copyfile(ROOT/'docs/OPENWRT.md',staging/'OPENWRT.md')
        (staging/'bundle.json').write_text(json.dumps({'version':__version__,'github_commit':revision,'dirty':dirty,'wheel_sha256':hashes},indent=2)+'\n')
        for path in staging.rglob('*'):path.chmod(0o755 if path.is_dir() else 0o644)
        output.parent.mkdir(parents=True,exist_ok=True)
        with tarfile.open(output,'w:gz') as archive:archive.add(staging,arcname=staging.name)
    return output
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--wheels',type=pathlib.Path);parser.add_argument('--output',type=pathlib.Path,default=ROOT/'dist/openwrt/serviceready-openwrt.tar.gz');args=parser.parse_args()
    if args.wheels:print(build(args.output,args.wheels))
    else:
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run([sys.executable,'-m','pip','download','--only-binary=:all:','--no-deps','--dest',folder,*DEPENDENCIES],check=True)
            print(build(args.output,pathlib.Path(folder)))
