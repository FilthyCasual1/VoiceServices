"""Produce independently installable addon archives and a core compatibility catalog."""
import hashlib,json,zipfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from voiceservices.version import __version__
root=Path(__file__).resolve().parents[1];destination=root/'packages/addons'/__version__;destination.mkdir(parents=True,exist_ok=True)
catalog={}
for source in sorted((root/'addon_sources').glob('*.py')):
    code=source.read_bytes();compile(code,str(source),'exec')
    metadata={'version':__version__,'api':1,'sha256':hashlib.sha256(code).hexdigest()};catalog[source.stem]=metadata
    with zipfile.ZipFile(destination/(source.stem+'-'+__version__+'.sraddon'),'w',zipfile.ZIP_DEFLATED) as archive:
        for name,content in [('manifest.json',json.dumps(dict(metadata,id=source.stem)).encode()),('module.py',code)]:
            entry=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;entry.external_attr=0o100644<<16
            archive.writestr(entry,content)
(root/'voiceservices/addon_catalog.json').write_text(json.dumps(catalog,indent=2)+'\n')
print(destination)
