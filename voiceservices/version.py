"""ServiceReady release version; update with tools/bump_version.py."""
__version__ = '1.27.14'
__codename__ = 'CrystalBlue'

__build__ = 18
import json,re
from pathlib import Path
try:
    __github_revision__=json.loads(Path(__file__).with_name('build_info.json').read_text()).get('github_commit','')
except (OSError,ValueError):__github_revision__=''
if not isinstance(__github_revision__,str) or not re.fullmatch('[a-f0-9]{40}',__github_revision__):__github_revision__=''
__display_version__ = __version__

if __github_revision__:__display_version__ += " " + __github_revision__[:12]
