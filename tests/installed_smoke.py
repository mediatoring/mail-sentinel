import json
import sys
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request
from urllib.parse import urlsplit
import venv

wheel=Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix='sentinel-install-') as directory:
    root=Path(directory)
    venv.create(root/'venv',with_pip=True)
    python=root/('venv/Scripts/python.exe' if os.name == 'nt' else 'venv/bin/python')
    subprocess.run([str(python),'-m','pip','install','--no-index','--no-deps',str(wheel)],check=True,cwd=root,stdout=subprocess.PIPE)
    subprocess.run([str(python),'-m','sentinel','export-demo'],check=True,cwd=root,stdout=subprocess.PIPE)
    assert len(list((root/'demo-emails').glob('*.eml')))==5
    check=subprocess.run([str(python),'-m','sentinel','check'],cwd=root,capture_output=True,text=True)
    assert check.returncode==2 and json.loads(check.stdout)['version']=='1.0.0rc1'
    for attempt in range(2):
        process=subprocess.Popen([str(python),'-m','sentinel','serve','--port','0'],cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            line=process.stdout.readline().strip()
            url=line.split('Mail Sentinel: ',1)[1]
            base=url.split('/#token=',1)[0]
            token=urlsplit(url).fragment.removeprefix('token=')
            for route in ['/', '/app.js', '/controls.js', '/i18n.js', '/style.css']:
                with urllib.request.urlopen(base+route,timeout=5) as response:
                    assert response.status==200 and response.read()
            req=urllib.request.Request(base+'/api/state',headers={'X-Sentinel-Token':token})
            with urllib.request.urlopen(req,timeout=5) as response:
                assert len(json.load(response)['messages'])==5
        finally:
            process.terminate()
            out,err=process.communicate(timeout=10)
            if os.name != 'nt':
                assert process.returncode==0,(process.returncode,err)
            assert not err,err
    backup=subprocess.run([str(python),'-m','sentinel','backup',str(root/'snapshot.sqlite3')],cwd=root,capture_output=True,text=True)
    assert backup.returncode==0,backup.stderr
print('PASS: clean offline wheel installation, demo assets, readiness, authenticated HTTP/UI assets, SIGTERM, restart and backup outside source checkout.')
