"""Open the existing local service, or start it in the background."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser
from .providers import NoRedirect


def publish_session(config, port, token, config_path):
    root = Path(config.data_dir)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=root, delete=False) as handle:
        json.dump({'port':port, 'token':token, 'config':str(Path(config_path).resolve())}, handle)
        pending = Path(handle.name)
    try:
        os.replace(pending, root/'browser-session.json')
    finally:
        pending.unlink(missing_ok=True)


def session_url(config, config_path):
    try:
        path = Path(config.data_dir)/'browser-session.json'
        if path.stat().st_size > 8192:
            return None
        info = json.loads(path.read_text('utf-8'))
        port, token = info['port'], info['token']
        if type(port) is not int or not 1 <= port <= 65535 or not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}',token):
            return None
        if info['config'] != str(Path(config_path).resolve()):
            return None
        base = f'http://127.0.0.1:{port}'
        request = urllib.request.Request(base+'/api/settings', headers={'X-Sentinel-Token':token})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=1) as response:
            if response.status != 200:
                return None
        return base+'/settings#token='+token
    except (OSError, ValueError, KeyError, TypeError):
        return None


def open_app(config, config_path, port=8765):
    url = session_url(config, config_path)
    if not url:
        root = Path(config.data_dir)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(root/'desktop.log', os.O_WRONLY|os.O_CREAT|os.O_APPEND, 0o600)
        with os.fdopen(fd,'ab') as log:
            options = {'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS} if os.name=='nt' else {'start_new_session':True}
            subprocess.Popen([sys.executable,'-m','sentinel','--config',str(Path(config_path).resolve()),'serve','--port',str(port)],
                             stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **options)
        deadline = time.monotonic()+15
        while time.monotonic()<deadline:
            url = session_url(config, config_path)
            if url:
                break
            time.sleep(.15)
        if not url:
            raise RuntimeError('The local application could not start. Check desktop.log in the data directory and whether the port is in use.')
    if not webbrowser.open(url):
        raise RuntimeError('The application is running, but the browser could not be opened. Check your default browser settings.')
    print('Mail Sentinel opened in your browser. The service runs in the background.')
