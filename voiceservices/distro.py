"""Detected distro logos from an allowlisted HTTPS source with a local cache."""
import html,platform,time
from pathlib import Path
from urllib.request import urlopen
from xml.etree import ElementTree as ET
ICONS={'openwrt':'openwrt','alpine':'alpinelinux','debian':'debian','ubuntu':'ubuntu','fedora':'fedora','arch':'archlinux','opensuse':'opensuse','opensuse-leap':'opensuse','opensuse-tumbleweed':'opensuse','linuxmint':'linuxmint','gentoo':'gentoo','nixos':'nixos','rhel':'redhat','rocky':'rockylinux','alma':'almalinux'}
def detected():
    try: return platform.freedesktop_os_release()
    except (AttributeError,OSError): return {'ID':'linux','PRETTY_NAME':platform.system()}
def logo(app):
    distro=detected();identifier=distro.get('ID','linux').lower();slug=ICONS.get(identifier)
    if identifier=='rocky':return Path(__file__).with_name('static').joinpath('distro-rocky.svg').read_bytes()
    root=Path(app.store.path).parent/'distro-logos';root.mkdir(parents=True,exist_ok=True)
    cache=root/((slug or 'linux')+'.svg')
    if cache.is_file() and not cache.is_symlink() and time.time()-cache.stat().st_mtime<86400: return cache.read_bytes()
    if slug:
        try:
            with urlopen('https://cdn.simpleicons.org/'+slug,timeout=2) as response: raw=response.read(65537)
            if len(raw)>65536: raise ValueError('Logo too large.')
            source=ET.fromstring(raw)
            if source.tag.rsplit('}',1)[-1]!='svg': raise ValueError('Invalid SVG.')
            # Rebuild only geometry; scripts, external references and embedded HTML are discarded.
            target=ET.Element('svg',{'xmlns':'http://www.w3.org/2000/svg','viewBox':'0 0 24 24','fill':'#527b96','role':'img'})
            ET.SubElement(target,'title').text=distro.get('PRETTY_NAME',identifier)
            paths=[node for node in source.iter() if node.tag.rsplit('}',1)[-1]=='path' and node.get('d')]
            if not paths: raise ValueError('Logo has no paths.')
            for node in paths: ET.SubElement(target,'path',{'d':node.get('d')})
            image=ET.tostring(target);temporary=cache.with_suffix('.tmp');temporary.write_bytes(image);temporary.replace(cache);return image
        except (OSError,ValueError,ET.ParseError): pass
    name=html.escape(distro.get('PRETTY_NAME',identifier))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 100"><rect x="1" y="1" width="158" height="98" fill="#e4e9ec" stroke="#829da9"/><text x="80" y="50" text-anchor="middle" font-family="Arial" font-size="12" fill="#31586b">'+name+'</text></svg>').encode()
