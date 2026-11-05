#!/usr/bin/env python3
"""Set login password locally; run with Python inside library container as uid 1024.
Mount secrets read-write ONLY for this one-shot command; never copy secrets into source.
"""
import getpass, json, os, secrets
from pathlib import Path
from werkzeug.security import generate_password_hash
path=Path('/secrets/auth.json')
config=json.loads(path.read_text()) if path.exists() else {'username':os.environ.get('SLIDES_USERNAME','admin'),'session_secret':secrets.token_hex(48)}
password=getpass.getpass('New password: ')
if len(password)<14:
    raise SystemExit('Use at least 14 characters.')
if password!=getpass.getpass('Confirm password: '):
    raise SystemExit('Passwords do not match.')
config.setdefault('share_copy_secret',secrets.token_hex(32))
config['password_hash']=generate_password_hash(password,method='pbkdf2:sha256:1000000')
config['session_secret']=secrets.token_hex(48) # invalidate all existing signed sessions
path.write_text(json.dumps(config))
os.chmod(path,0o600)
(path.parent/'LOGIN.txt').unlink(missing_ok=True)
print('Password updated. Restart the library service to load it.')
