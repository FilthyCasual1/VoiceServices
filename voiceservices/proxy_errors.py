"""Static proxy error pages remain available when the portal process is offline."""
import html,json,sqlite3,time
from contextlib import closing
from pathlib import Path
from .version import __version__

def publish(config,root):
 folder=root/'usr/share/nginx/html/serviceready-errors';folder.mkdir(parents=True,exist_ok=True)
 brand={'title':'CasualNetworks','subtitle':'ServiceReady INSAP',**config.get('branding',{})}
 if config.get('database'):
  try:
   with closing(sqlite3.connect(Path(config['database']).resolve().as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
    row=db.execute("SELECT value FROM portal_settings WHERE key='branding'").fetchone()
    if row:brand.update(json.loads(row[0]))
  except (sqlite3.Error,OSError,ValueError):pass
 def write(name,data):
  target=folder/name
  if not target.exists() or target.read_bytes()!=data:
   temporary=target.with_suffix(target.suffix+'.new');temporary.write_bytes(data);temporary.chmod(0o644);temporary.replace(target)
 assets=Path(__file__).with_name('static')
 for name in ('style.css','brand-arrow.svg','masthead.png','proxy-reconnect.js'):write(name,(assets/name).read_bytes())
 prefix='/_serviceready_error_assets/'
 for name,title,body,retry in [
  ('unavailable.html','We’ll be back shortly','The portal is temporarily unavailable. It may be restarting or applying an update. Your browser will check for its return automatically. If this continues, contact your system administrator. Any submitted change may already have completed; check its status before submitting again.',True),
  ('request.html','Your request could not be accepted','The web server could not accept this request. If you were uploading a file, check its size against the configured upload limit. Return to the portal and review your request before trying again.',False)]:
  text='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+' — '+html.escape(str(brand['title']))+'</title><link rel="stylesheet" href="'+prefix+'style.css">'+('<script defer src="'+prefix+'proxy-reconnect.js"></script>' if retry else '')+'</head><body><header class="masthead-wide"><div class="brand"><img class="wide-photo" src="'+prefix+'masthead.png" alt=""><img class="brand-arrow" src="'+prefix+'brand-arrow.svg" alt=""><div><strong>'+html.escape(str(brand['title']))+'</strong><small>'+html.escape(str(brand['subtitle']))+'</small></div></div><div class="account"><div class="account-details"><div>Service temporarily unavailable</div></div></div></header><nav><a href="/">Home</a></nav><div class="layout"><main><div class="crumb">'+html.escape(str(brand['title']))+'</div><h1>'+html.escape(title)+'</h1><div class="panel"><p>'+html.escape(body)+'</p>'+('<p data-proxy-status role="status" aria-live="polite">Checking for the portal every five seconds…</p>' if retry else '')+'<p><a href="/">Return to the portal</a></p></div></main></div><footer><span>'+html.escape(str(brand['title']))+' | ServiceReady '+__version__+'</span><span class="footer-copyright">Copyright © '+str(time.localtime().tm_year)+' CasualNetworks.</span></footer></body></html>'
  write(name,text.encode())
 return folder
