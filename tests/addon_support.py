import io,json,zipfile
from pathlib import Path

def package(name):
    code=(Path('addon_sources')/(name+'.py')).read_bytes()
    metadata=json.loads(Path('voiceservices/addon_catalog.json').read_text())[name]
    target=io.BytesIO()
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json',json.dumps(dict(metadata,id=name)));archive.writestr('module.py',code)
    return target.getvalue()
def install(app,name): return app.modules.install(package(name))
