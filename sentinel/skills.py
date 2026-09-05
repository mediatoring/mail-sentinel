"""Explicit administrator-owned procedures loaded from bounded local skill directories."""
import hashlib
import re
import tomllib
from pathlib import Path


def load_skills(config, allowed_tools):
    root=Path(config.skills_dir).resolve()
    result=[]
    if len(config.enabled_skills)>10:
        raise ValueError('Too many enabled skills')
    for name in config.enabled_skills:
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',name):
            raise ValueError('Invalid skill name')
        folder=(root/name).resolve()
        if folder.parent!=root:
            raise ValueError('Skill path escapes configured directory')
        paths=[folder/'manifest.toml',folder/'SKILL.md']
        for p in paths:
            if p.resolve().parent!=folder or p.stat().st_size>16000:
                raise ValueError('Invalid or oversized skill file')
        manifest=tomllib.loads(paths[0].read_text('utf-8'))
        text=paths[1].read_text('utf-8')
        if manifest.get('version')!=1 or manifest.get('id')!=name or not isinstance(manifest.get('tools'),list):
            raise ValueError('Invalid skill manifest')
        if not set(manifest['tools'])<=set(allowed_tools):
            raise ValueError('Skill requires unavailable or disabled tools')
        result.append({'id':name,'sha256':hashlib.sha256(paths[0].read_bytes()+b'\0'+paths[1].read_bytes()).hexdigest(),'instructions':text})
    return result
