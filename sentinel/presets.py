"""Administrator-owned local presets; credentials never enter HTTP responses."""
import dataclasses
import json
from pathlib import Path
import re
import tomllib
from .config import Config

IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}')


def directory(config_path):
    return Path(config_path).resolve().parent / '.local-presets'


def checked_file(root, name, limit):
    path = root / name
    if path.resolve().parent != root.resolve() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('Invalid local preset file')
    return path


def list_presets(config_path):
    root = directory(config_path)
    return [{'id':p.stem, 'name':p.stem.replace('-', ' ')}
            for p in sorted(root.glob('*.toml'))
            if IDENTIFIER.fullmatch(p.stem) and not p.is_symlink() and p.is_file()][:100]


def load_preset(config_path, ident, current, editable):
    if not isinstance(ident,str) or not IDENTIFIER.fullmatch(ident):
        raise ValueError('Invalid local preset identifier')
    root = directory(config_path)
    try:
        supplied = tomllib.loads(checked_file(root,ident+'.toml',65536).read_text('utf-8'))
        values = dataclasses.asdict(current)
        if set(supplied) - set(values):
            raise ValueError('Unknown preset setting')
        for key in ('data_dir','skills_dir','organization_file','data_sources_file'):
            if key in supplied and supplied[key]:
                supplied[key] = str((root / supplied[key]).resolve())
        values.update(supplied)
        Config(**values).validate()
        def startup_matches(key):
            before, after = getattr(current,key), values[key]
            if key in ('data_dir','skills_dir'):
                return Path(before).resolve() == Path(after).resolve()
            return before == after
        if any(not startup_matches(key) for key in values if key not in editable):
            raise ValueError('Preset requires restarting the application')
        result = {key:values[key] for key in editable}
        credential_path = root / (ident+'.credentials.json')
        if credential_path.exists():
            refs = json.loads(checked_file(root,credential_path.name,8192).read_text('utf-8'))
            if not isinstance(refs,dict) or set(refs)-{'api_key_file','imap_password_file'}:
                raise ValueError('Invalid local credential references')
            for key,value in refs.items():
                if not isinstance(value,str):
                    raise ValueError('Invalid local credential reference')
                path = (root/value).resolve()
                allowed = (root.resolve(), (root.parent/'.acceptance').resolve())
                if not any(path.is_relative_to(parent) for parent in allowed) or not path.is_file() or path.stat().st_size>4000:
                    raise ValueError('Invalid local credential file')
                secret = path.read_text('utf-8').strip()
                if not secret:
                    raise ValueError('Empty local credential file')
                result[key.removesuffix('_file')] = secret
        return result
    except Exception:
        # File names, TOML values and credential contents stay on the host.
        raise ValueError('Local preset could not be loaded; check its files and startup settings') from None
