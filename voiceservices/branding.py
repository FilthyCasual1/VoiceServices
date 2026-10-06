"""Core branding and editable home blocks, independent of service addons."""
import html,json,re,secrets,struct
from datetime import datetime
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from pathlib import Path
from . import regional
from urllib.parse import urlsplit
E=lambda value:html.escape(str(value),quote=True)

def initialize(app):
    with app.store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS home_blocks(id INTEGER PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,url TEXT NOT NULL,position INTEGER NOT NULL,module TEXT NOT NULL,enabled INTEGER NOT NULL)')
        if not db.execute("SELECT 1 FROM module_metadata WHERE key='home-blocks-seeded'").fetchone():
            blocks=[('1. Get an account','Create an account to access the services available on your network. Your administrator can help you get the access you need.','/create-account',10,'',1),('2. Sign in','Sign in to manage your account and use your network services. You can update your profile and security settings in My Account.','/login',20,'',1),('3. Set up your services','Find the tools and guidance you need to set up storage, voice, email and domain services. Available options depend on the addons installed on this portal. Contact your administrator if you need help getting started.','',30,'',1),('Downloads and setup','Download the internal tools and applications you need for your devices, along with any setup instructions provided by your administrator.','/downloads',40,'downloads',1)]
            db.executemany('INSERT INTO home_blocks(title,body,url,position,module,enabled) VALUES(?,?,?,?,?,?)',blocks)
            db.execute("INSERT INTO module_metadata VALUES('home-blocks-seeded')")
        if 'audience' not in {r[1] for r in db.execute('PRAGMA table_info(home_blocks)')}:
            db.execute("ALTER TABLE home_blocks ADD COLUMN audience TEXT NOT NULL DEFAULT 'guest'")
            db.execute("INSERT INTO home_blocks(title,body,url,position,module,enabled,audience) SELECT title,body,url,position,module,enabled,'signed-in' FROM home_blocks WHERE url NOT IN ('/login','/create-account')")
            db.execute("INSERT INTO home_blocks(title,body,url,position,module,enabled,audience) VALUES('My Account','Manage your profile, password, two-factor authentication and notifications in one place.','/account',10,'',1,'signed-in')")
        if not db.execute("SELECT 1 FROM module_metadata WHERE key='setup-copy-v1'").fetchone():
            db.execute('UPDATE home_blocks SET body=? WHERE title=? AND body=?',('Create an account to access the services available on your network. Your administrator can help you get the access you need.', '1. Get an account', 'Create your account to get started. Your administrator assigns access to the services available on your network.'))
            db.execute('UPDATE home_blocks SET body=? WHERE title=? AND body=?',('Sign in to manage your account and use your network services. You can update your profile and security settings in My Account.', '2. Sign in', 'Sign in to configure your services and manage your account settings. Use My Account to change your password.'))
            db.execute('UPDATE home_blocks SET body=? WHERE title=? AND body=?',('Find the tools and guidance you need to set up storage, voice, email and domain services. Available options depend on the addons installed on this portal. Contact your administrator if you need help getting started.', '3. Set up your services', 'Storage: configure network shares and shared storage.\nVoice: set up phones and calling accounts.\nEmail: configure mailboxes and email clients.\nDomain services: set up your network identity and enroll devices.\nAvailable tools depend on the installed modules. Ask your administrator for setup details.'))
            db.execute('UPDATE home_blocks SET body=? WHERE title=? AND body=?',('Download the internal tools and applications you need for your devices, along with any setup instructions provided by your administrator.', 'Downloads and setup', 'Download internal tools and applications for your machines.'))
            db.execute('UPDATE home_blocks SET body=? WHERE title=? AND body=?',('Manage your profile, password, two-factor authentication and notifications in one place.', 'My Account', 'Manage your profile, security and notifications.'))
            db.execute("INSERT INTO module_metadata VALUES('setup-copy-v1')")
        if not db.execute("SELECT 1 FROM module_metadata WHERE key='friendly-copy-v1'").fetchone():
            db.execute('UPDATE home_blocks SET body=? WHERE title=? AND body=?',('Create an account to access the services available on your network. Your administrator can help you get the access you need.', '1. Get an account', 'Create an account before setting up your services. Ask your administrator for the access you need, then check that your account works before relying on it.'))
            db.execute('UPDATE home_blocks SET body=? WHERE title=? AND body=?',('Sign in to manage your account and use your network services. You can update your profile and security settings in My Account.', '2. Sign in', 'Sign in and get your account sorted first. Set your password and security options in My Account before using this portal in production.'))
            db.execute('UPDATE home_blocks SET body=? WHERE title=? AND body=?',('Find the tools and guidance you need to set up storage, voice, email and domain services. Available options depend on the addons installed on this portal. Contact your administrator if you need help getting started.', '3. Set up your services', 'Get your services configured and tested before putting them into production.\nStorage: verify shares, permissions and backups.\nVoice: test phone registration and calls.\nEmail: check mailbox access and delivery.\nDomain services: verify identities and device enrollment.\nInstall only the addons you need. A working portal does not mean your services are ready—test the full setup.'))
            db.execute('UPDATE home_blocks SET body=? WHERE title=? AND body=?',('Download the internal tools and applications you need for your devices, along with any setup instructions provided by your administrator.', 'Downloads and setup', 'Get the tools you need, configure them, and test them on a spare machine before rolling them out.'))
            db.execute('UPDATE home_blocks SET body=? WHERE title=? AND body=?',('Manage your profile, password, two-factor authentication and notifications in one place.', 'My Account', 'Check your profile, change default credentials, and set up two-factor authentication before using this account in production.'))
            db.execute("INSERT INTO module_metadata VALUES('friendly-copy-v1')")
SESSION_TEXT = {
    'logout_title': ('Logout heading', 'End your session?'),
    'logout_subtitle': ('Logout subtitle', 'Confirm before signing out.'),
    'logout_message': ('Logout question', 'Are you sure you wish to end your session?'),
    'logout_detail': ('Logout explanation', 'You can sign in again whenever you need your network services.'),
    'logout_cancel': ('Keep session button', 'Stay signed in'),
    'logout_confirm': ('End session button', 'End session'),
    'logged_out_title': ('Session-ended heading', 'Session ended'),
    'logged_out_subtitle': ('Session-ended subtitle', 'You have been logged out.'),
    'logged_out_message': ('Session-ended message', 'Your session has ended. Returning to sign in in five seconds.'),
    'logged_out_link': ('Return to sign-in link', 'Sign in now'),
}

def defaults(app):
    value=dict({'title':'CasualNetworks','subtitle':'ServiceReady INSAP','masthead_layout':'wide','login_title':'Welcome back','create_title':'Create your account','login_subtitle':'Access your account and network services.','create_subtitle':'Create an account to get started with your network services.','login_greeting':'custom','create_greeting':'custom','greeting_timezone':'UTC','login_disclaimer_enabled':False,'login_disclaimer':''},**app.config.get('branding',{}))
    for key,old,new in [('login_subtitle','Sign in, finish the setup, and test before going live.','Access your account and network services.'),('create_subtitle','Get your account ready before putting services into production.','Create an account to get started with your network services.'),('login_subtitle','Your network services, in one place.','Access your account and network services.'),('create_subtitle','Your starting point for network services.','Create an account to get started with your network services.')]:
        if value.get(key)==old: value[key]=new
    if value['title']=='ServiceReady': value['title']='CasualNetworks'
    value.setdefault('global_timezone',value.get('greeting_timezone','UTC'))
    value.setdefault('date_format','iso');value.setdefault('time_format','24-hour')
    for key, (_, text) in SESSION_TEXT.items(): value.setdefault(key,text)
    return value
def valid_url(value):
    if not value: return True
    if any(ord(c)<33 for c in value): return False
    if value.startswith('/') and not value.startswith('//') and '\\' not in value: return True
    p=urlsplit(value);return p.scheme in ('http','https') and bool(p.netloc) and not p.username and not p.password

def change(app,section,data):
    if section=='branding':
        title=data.get('title','').strip();subtitle=data.get('subtitle','').strip()
        if not 1<=len(title)<=80 or len(subtitle)>160: raise ValueError('Enter a title of 1–80 characters and a subtitle of at most 160 characters.')
        value=defaults(app);previous_zone=value['global_timezone'];value.update(title=title,subtitle=subtitle)
        layout=data.get('masthead_layout',value.get('masthead_layout','wide'))
        if layout not in ('wide','compact'): raise ValueError('Choose a valid masthead layout.')
        value['masthead_layout']=layout
        for key in ('login_title','create_title','login_subtitle','create_subtitle',*SESSION_TEXT):
            entry=data.get(key,value[key]).strip()
            if not 1<=len(entry)<=160: raise ValueError('Box headings and subtitles must contain 1–160 characters.')
            value[key]=entry
        for key in ('login_greeting','create_greeting'):
            entry=data.get(key,value[key])
            if entry not in ('custom','time'): raise ValueError('Choose custom or time-based greeting.')
            value[key]=entry
        zone=data.get('global_timezone',data.get('greeting_timezone',value['global_timezone'])).strip()
        try: ZoneInfo(zone)
        except (ZoneInfoNotFoundError,ValueError): raise ValueError('Choose a valid IANA greeting time zone.')
        value['global_timezone']=zone;value['greeting_timezone']=zone
        for key,options in [('date_format',regional.DATE_FORMATS),('time_format',regional.TIME_FORMATS)]:
            entry=data.get(key,value[key])
            if entry not in options: raise ValueError('Choose a supported date and time format.')
            value[key]=entry
        enabled=data.get('login_disclaimer_enabled','yes' if value['login_disclaimer_enabled'] else 'no')
        if enabled not in ('yes','no'): raise ValueError('Choose whether to show the login disclaimer.')
        disclaimer=data.get('login_disclaimer',value['login_disclaimer']).strip()
        if len(disclaimer)>4000 or (enabled=='yes' and not disclaimer): raise ValueError('Enter disclaimer text of up to 4000 characters when enabled.')
        value.update(login_disclaimer_enabled=enabled=='yes',login_disclaimer=disclaimer)
        if data.get('reset_logo')=='yes': value.pop('logo',None)
        if data.get('reset_masthead')=='yes': value.pop('masthead',None)
        if data.get('reset_header_fill')=='yes': value.pop('header-fill',None)
        save(app,value)
        if previous_zone!=zone:
            from . import update_schedule
            update_schedule.rebase_global(app)
        return 'Appearance saved.'
    action=data.get('action','save')
    with app.store.connect() as db:
        if action=='delete': db.execute('DELETE FROM home_blocks WHERE id=?',(int(data.get('block','')),));return 'Block removed.'
        title=data.get('title','').strip();body=data.get('body','').strip();url=data.get('url','').strip();module=data.get('module','')
        from .modules import CATALOG
        if not 1<=len(title)<=120 or len(body)>5000 or not valid_url(url) or (module and module not in CATALOG): raise ValueError('Check block title, text, link and addon selection.')
        try: position=int(data.get('position','0'))
        except ValueError: raise ValueError('Enter a numeric block position.')
        audience=data.get('audience','guest')
        if audience not in ('guest','signed-in'): raise ValueError('Choose Guest or Signed-in users.')
        values=(title,body,url,position,module,int(data.get('enabled')=='yes'),audience)
        if data.get('block'):
            db.execute('UPDATE home_blocks SET title=?,body=?,url=?,position=?,module=?,enabled=?,audience=? WHERE id=?',values+(int(data['block']),))
        else: db.execute('INSERT INTO home_blocks(title,body,url,position,module,enabled,audience) VALUES(?,?,?,?,?,?,?)',values)
    return 'Home block saved.'
def save(app,value):
    with app.store.connect() as db: db.execute("INSERT OR REPLACE INTO portal_settings VALUES('branding',?)",(json.dumps(value),))
    app.config['branding']=value

def image_type(raw):
    if len(raw)>1024**2: raise ValueError('Logo must be at most 1 MiB.')
    if raw.startswith(b'\x89PNG\r\n\x1a\n') and len(raw)>=24 and raw[12:16]==b'IHDR':
        width,height=struct.unpack('>II',raw[16:24]);suffix='png'
        if not 0<width<=4096 or not 0<height<=4096: raise ValueError('Logo dimensions must be at most 4096 pixels.')
    elif raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9'): suffix='jpg'
    else: raise ValueError('Upload a PNG or JPEG logo.')
    return suffix

def upload_logo(app,raw,kind='logo'):
    suffix=image_type(raw)
    from .data_volume import folder
    root=folder(app,'branding');root.mkdir(parents=True,exist_ok=True)
    name=secrets.token_hex(16)+'.'+suffix;(root/name).write_bytes(raw)
    value=defaults(app);old=value.get(kind);value[kind]=name;save(app,value)
    if old and re.fullmatch('[a-f0-9]{32}\\.(png|jpg)',old): (root/old).unlink(missing_ok=True)

def logo(app,kind='logo'):
    name=defaults(app).get(kind,'')
    if not re.fullmatch('[a-f0-9]{32}\\.(png|jpg)',name): return None
    from .data_volume import folder
    try:path=folder(app,'branding')/name
    except ValueError:return None
    if not path.is_file() or path.is_symlink(): return None
    return path.read_bytes(),'image/png' if name.endswith('.png') else 'image/jpeg'

def home(app,user=None):
    content='<p class="notice">Welcome to your network services portal. Find setup guidance, useful tools and account settings here.</p>'
    with app.store.connect() as db:
        for row in db.execute('SELECT * FROM home_blocks WHERE enabled=1 AND audience=? ORDER BY position,id',('signed-in' if user and user['role']!='guest' else 'guest',)):
            if row['module'] and not app.modules.installed(row['module']): continue
            content+='<h2>'+E(row['title'])+'</h2><div class="panel"><p>'+E(row['body']).replace('\n','<br>')+'</p>'
            if row['url']: content+='<p><a href="'+E(row['url'])+'">'+E(row['title'])+'</a></p>'
            content+='</div>'
    return content

def render(app,section,user):
    csrf='<input type="hidden" name="csrf" value="'+E(user['csrf'])+'">'
    if section=='branding':
        value=defaults(app)
        def field(label,control): return '<div class="setting-field"><label>'+E(label)+'</label>'+control+'</div>'
        def text_field(key,label,limit=160): return field(label,'<input name="'+key+'" maxlength="'+str(limit)+'" value="'+E(value[key])+'">')
        def group(label,body,opened=False): return '<details class="settings-section"'+(' open' if opened else '')+'><summary>'+label+'</summary><div class="settings-grid">'+body+'</div></details>'
        identity=text_field('title','Brand title',80)+text_field('subtitle','Subtitle')
        identity+=field('Masthead layout','<select name="masthead_layout"><option value="wide">Full width, always visible</option><option value="compact"'+(' selected' if value.get('masthead_layout')=='compact' else '')+'>Compact right image, hide on narrow screens</option></select>')
        for key,label,reset in [('reset_logo','Logo','Use default arrow'),('reset_masthead','Masthead image','Use default image'),('reset_header_fill','Secondary masthead','Clear secondary masthead')]:
            identity+=field(label,'<select name="'+key+'"><option value="no">Keep current image</option><option value="yes">'+reset+'</option></select>')
        groups=group('Brand and masthead',identity,True)
        locale=field('Global time zone',regional.timezone_select('global_timezone',value['global_timezone']))
        for key,label,options in [('date_format','Date format',regional.DATE_FORMATS),('time_format','Time format',regional.TIME_FORMATS)]:
            locale+=field(label,'<select name="'+key+'">'+''.join('<option value="'+code+'"'+(' selected' if value[key]==code else '')+'>'+E(item[1])+'</option>' for code,item in options.items())+'</select>')
        groups+=group('Date, time and time zone',locale)
        for kind,label in [('login','Sign-in box'),('create','Create-account box')]:
            body=text_field(kind+'_title','Heading')+text_field(kind+'_subtitle','Subtitle')
            body+=field('Greeting','<select name="'+kind+'_greeting"><option value="custom">Use custom heading</option><option value="time"'+(' selected' if value[kind+'_greeting']=='time' else '')+'>Good morning / afternoon / evening</option></select>')
            groups+=group(label,body)
        body=field('Show disclaimer','<select name="login_disclaimer_enabled"><option value="no">Off</option><option value="yes"'+(' selected' if value['login_disclaimer_enabled'] else '')+'>On</option></select>')
        body+='<div class="setting-field setting-wide"><label>Disclaimer text</label><textarea name="login_disclaimer" maxlength="4000" rows="3">'+E(value['login_disclaimer'])+'</textarea></div>'
        groups+=group('Login disclaimer',body)
        groups+=group('Logout confirmation', ''.join(text_field(key,label) for key,(label,_) in SESSION_TEXT.items() if key.startswith('logout_')))
        groups+=group('Session-ended box', ''.join(text_field(key,label) for key,(label,_) in SESSION_TEXT.items() if key.startswith('logged_out_')))
        content='<div class="compact-settings"><form method="post">'+csrf+groups+'<button>Save Appearance</button></form><details class="settings-section"><summary>Upload images</summary><div class="image-upload-grid">'
        images=[('/admin/branding/upload','Brand logo','40 × 40 px recommended; 30 × 30 px on narrow screens.'),('/admin/branding/masthead/upload','Masthead image','Wide: 1284 × 963 px recommended, fixed 963 px height cropped into a 68 px header. Compact: 600 × 68 px window, fixed 700 px image width.'),('/admin/branding/header-fill/upload','Secondary masthead','600 × 68 px recommended; fixed 68 px height, cropped to the available width and aligned right.')]
        for url,label,help_text in images:
            content+='<div class="panel"><form action="'+url+'" method="post" enctype="multipart/form-data">'+csrf+'<label>'+label+' (PNG or JPEG, up to 1 MiB)</label><p class="muted">'+help_text+'</p><input type="file" name="file" accept="image/png,image/jpeg" required><button>Upload '+label.lower()+'</button></form></div>'
        return content+'</div></details><p class="muted">Appearance changes apply to all portal pages.</p></div>'
    from .modules import CATALOG
    def form(row):
        fields='<div class="panel"><form method="post">'+csrf+'<input type="hidden" name="block" value="'+E(row.get('id',''))+'"><div class="settings-grid">'
        for key,label,limit in [('title','Block title',120),('url','Link (optional)',500),('position','Position',10)]: fields+='<div class="setting-field"><label>'+label+'</label><input name="'+key+'" maxlength="'+str(limit)+'" value="'+E(row.get(key,''))+'"></div>'
        fields+='<div class="setting-field"><label>Home page</label><select name="audience"><option value="guest">Guest</option><option value="signed-in"'+(' selected' if row.get('audience')=='signed-in' else '')+'>Signed-in users</option></select></div>'
        fields+='<div class="setting-field"><label>Show when addon is installed</label><select name="module"><option value="">Always</option>'
        for key,(title,_) in CATALOG.items(): fields+='<option value="'+key+'"'+(' selected' if row.get('module')==key else '')+'>'+E(title)+'</option>'
        fields+='</select></div><div class="setting-field"><label>Visibility</label><select name="enabled"><option value="yes">Visible</option><option value="no"'+(' selected' if row.get('enabled',1)==0 else '')+'>Hidden</option></select></div><div class="setting-field setting-wide"><label>Text</label><textarea name="body" rows="3" maxlength="5000">'+E(row.get('body',''))+'</textarea></div></div><button name="action" value="save">'+('Save block' if row.get('id') else 'Add block')+'</button>'
        if row.get('id'): fields+='<button name="action" value="delete">Remove block</button>'
        return fields+'</form></div>'
    pages=[('/','Home'),('/create-account','Create an account'),('/login','Sign in'),('/account','My Account'),('/admin','Administration')]
    addon_pages={'downloads':[('/downloads','Downloads')],'voice':[('/my-phone','My Phone'),('/applications','Phone applications'),('/directory','Directory'),('/recordings','Recordings')],'esxi':[('/esxi','ESXi Management')]}
    for key,links in addon_pages.items():
        if app.modules.installed(key): pages.extend(links)
    content='<div class="compact-settings"><details class="settings-section"><summary>Page links legend</summary><div class="panel"><p>Use these paths in a block’s Link field. Account and administration pages require sign-in; administration requires administrator access.</p><table><tr><th>Page</th><th>Link path</th></tr>'+''.join('<tr><td>'+E(title)+'</td><td><code>'+E(url)+'</code></td></tr>' for url,title in pages)+'</table><p>Addon page links are shown only while their addon is installed.</p></div></details><p>Edit your home-page blocks below. Plain text and optional links are supported.</p>'
    with app.store.connect() as db:
        for audience,label in [('guest','Guest home'),('signed-in','Signed-in home')]:
            content+='<h3>'+label+'</h3>'
            for row in db.execute('SELECT * FROM home_blocks WHERE audience=? ORDER BY position,id',(audience,)): content+='<details class="settings-section"><summary>'+E(row['title'])+' <span class="muted">— '+('Visible' if row['enabled'] else 'Hidden')+' · Position '+str(row['position'])+'</span></summary>'+form(dict(row))+'</details>'
    return content+'<details class="settings-section"><summary>Add a block</summary>'+form({'position':50})+'</details></div>'

def box_text(app,kind):
    value=defaults(app);title=value[kind+'_title']
    if value[kind+'_greeting']=='time':
        hour=datetime.now(regional.zone(app)).hour
        title='Good morning' if hour<12 else 'Good afternoon' if hour<18 else 'Good evening'
    return title,value[kind+'_subtitle']
