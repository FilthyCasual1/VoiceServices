"""Uploaded-content paths must never fall back to the boot disk."""
import os,subprocess
from pathlib import Path
def require(config):
 mount=config.get('data_mount')
 if not mount:return
 if not os.path.ismount(mount):raise ValueError('Upload disk is unavailable. Mount the configured volume before accessing uploaded content.')
 try:uuid=subprocess.check_output(['findmnt','-n','-o','UUID','--mountpoint',mount],text=True,timeout=5).strip()
 except (OSError,subprocess.SubprocessError):raise ValueError('Unable to verify the upload volume.') from None
 if uuid!=config.get('data_disk_uuid'):raise ValueError('A different disk is mounted at the upload location.')
def folder(app,name):
 require(app.config)
 return Path(app.config['data_mount'])/name if app.config.get('data_mount') else Path(app.store.path).parent/name
