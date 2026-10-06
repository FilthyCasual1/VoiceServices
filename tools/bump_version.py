"""Increment ServiceReady's version and record a release note."""
import argparse
from datetime import date
from pathlib import Path
import re

parser = argparse.ArgumentParser()
parser.add_argument('part', choices=('patch', 'minor', 'major'))
parser.add_argument('note', help='Short description of the change')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
source = root / 'voiceservices/version.py'
text = source.read_text()
match = re.search(r"__version__ = '([0-9]+)\.([0-9]+)\.([0-9]+)'", text)
parts = list(map(int, match.groups()))
index = {'major':0, 'minor':1, 'patch':2}[args.part]
parts[index] += 1
for n in range(index+1, 3): parts[n] = 0
version = '.'.join(map(str, parts))
text=text[:match.start()] + "__version__ = '" + version + "'" + text[match.end():]
build_match=re.search(r'__build__ = (\d+)',text)
build=int(build_match[1])+1 if build_match else 1
if build_match:text=text[:build_match.start()]+'__build__ = '+str(build)+text[build_match.end():]
else:text+='\n__build__ = '+str(build)+'\n__display_version__ = __version__ + \" (build \" + str(__build__) + \")\"\n'
source.write_text(text)
changelog = root / 'CHANGELOG.md'
previous = changelog.read_text().removeprefix('# Changelog\n\n') if changelog.exists() else ''
changelog.write_text(f'# Changelog\n\n## {version} — {date.today().isoformat()}\n\n{args.note}\n\n'+previous)
print(version)
