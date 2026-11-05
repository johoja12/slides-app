"""Private LAN slide library. Caddy terminates HTTPS; this app is internal only."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from flask import Response, Flask, abort, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import check_password_hash
import pptx_preview

ROOT = Path(os.environ.get('SLIDES_ROOT', '/library')).resolve()
CONFIG = json.loads(Path(os.environ.get('SLIDES_CONFIG', '/secrets/auth.json')).read_text())
DB = os.environ.get('SLIDES_DB', '/state/auth.sqlite3')
PUBLIC_ORIGIN = os.environ.get('PUBLIC_ORIGIN', 'https://localhost:8447').rstrip('/')
app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))
app.config.update(SECRET_KEY=CONFIG['session_secret'], SESSION_COOKIE_NAME='__Host-slides',
    SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12), MAX_CONTENT_LENGTH=16384,
    TRUSTED_HOSTS=[host.strip() for host in os.environ.get('SLIDES_TRUSTED_HOSTS',
        ','.join(dict.fromkeys(['localhost','127.0.0.1',urlsplit(PUBLIC_ORIGIN).hostname or 'localhost']))).split(',') if host.strip()])

@contextmanager
def db():
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute('CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, expires REAL NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS attempts (ip TEXT NOT NULL, stamp REAL NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS shares (id INTEGER PRIMARY KEY, token TEXT UNIQUE NOT NULL, deck TEXT NOT NULL, created REAL NOT NULL, expires REAL, revoked INTEGER NOT NULL DEFAULT 0)')
    columns={r[1] for r in conn.execute('PRAGMA table_info(shares)')}
    if not {'copy_seed','copy_token_hash'}.issubset(columns):
        conn.execute('BEGIN IMMEDIATE')
        columns={r[1] for r in conn.execute('PRAGMA table_info(shares)')}
        for column in ('copy_seed','copy_token_hash'):
            if column not in columns:
                conn.execute(f'ALTER TABLE shares ADD COLUMN {column} TEXT')
        conn.commit()
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS shares_copy_token_idx ON shares(copy_token_hash)')
    conn.execute('CREATE TABLE IF NOT EXISTS deck_preferences (deck TEXT PRIMARY KEY, favorite INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0,1)), pinned INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0,1)))')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def safe_next(value):
    # Prevent network-path redirects, control characters and browser backslash normalization.
    if not value or not value.startswith('/') or value.startswith('//') or '\\' in value or any(ord(c)<32 for c in value):
        return '/'
    p = urlsplit(value)
    return value if not p.netloc and not p.scheme and p.path != '/login' else '/'


def logged_in():
    token = session.get('token')
    if not token:
        return False
    with db() as conn:
        return conn.execute('SELECT 1 FROM sessions WHERE token=? AND expires>?', (token_hash(token),time.time())).fetchone() is not None


@app.before_request
def protect():
    if request.routing_exception is not None and request.routing_exception.code==404:
        return
    if request.endpoint in ('login','health','shared','shared_file','slide_navigation','shared_pptx','shared_pptx_data','shared_viewer'):
        return
    if not logged_in():
        return redirect(url_for('login', next=safe_next(request.full_path.rstrip('?'))))


@app.after_request
def headers(response):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    # Existing decks use inline scripts/styles. Keep them functional; restrict embedding.
    response.headers['Content-Security-Policy'] = "frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
    return response


@app.route('/login', methods=['GET','POST'])
def login():
    if logged_in():
        return redirect(safe_next(request.args.get('next')))
    session.setdefault('csrf', secrets.token_urlsafe(32))
    error = None
    status = 200
    destination = safe_next(request.values.get('next'))
    if request.method == 'POST':
        if not hmac.compare_digest(request.form.get('csrf',''), session['csrf']):
            abort(400)
        ip = request.headers.get('X-Real-IP', request.remote_addr or 'unknown')
        now = time.time()
        # Serialize the count + reservation so concurrent requests cannot bypass limits.
        with db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('DELETE FROM attempts WHERE stamp<?',(now-900,))
            conn.execute('DELETE FROM sessions WHERE expires<?',(now,))
            count = conn.execute('SELECT count(*) FROM attempts WHERE ip=?',(ip,)).fetchone()[0]
            total = conn.execute('SELECT count(*) FROM attempts').fetchone()[0]
            limited = count>=10 or total>=100
            if not limited:
                conn.execute('INSERT INTO attempts VALUES (?,?)',(ip,now))
        if limited:
            error, status = 'Too many attempts. Try again in 15 minutes.', 429
        else:
            valid_password = check_password_hash(CONFIG['password_hash'], request.form.get('password',''))
            valid_user = hmac.compare_digest(request.form.get('username','').encode(), CONFIG['username'].encode())
            if valid_user and valid_password:
                session.clear()
                session.permanent = True
                session['csrf'] = secrets.token_urlsafe(32)
                session['token'] = secrets.token_urlsafe(48)
                with db() as conn:
                    conn.execute('INSERT INTO sessions VALUES (?,?)',(token_hash(session['token']), now+43200))
                    conn.execute('DELETE FROM attempts WHERE ip=?',(ip,))
                return redirect(destination)
            error, status = 'Username or password is incorrect.', 401
    return render_template('login.html', error=error, destination=destination), status


@app.post('/logout')
def logout():
    if not hmac.compare_digest(request.form.get('csrf',''), session.get('csrf','!')):
        abort(400)
    with db() as conn:
        conn.execute('DELETE FROM sessions WHERE token=?',(token_hash(session.get('token','')),))
    session.clear()
    return redirect('/login')


def safe_file(relative):
    candidate = ROOT / relative
    try:
        parts = candidate.relative_to(ROOT).parts
        if not parts or any(p.startswith('.') for p in parts):
            abort(404)
        current = ROOT
        for part in parts:
            current = current / part
            if current.is_symlink():
                abort(404)
        candidate.resolve().relative_to(ROOT)
    except ValueError:
        abort(404)
    return candidate



def deck_modified(folder):
    """Latest content/asset mtime, preserving original dates when decks are copied."""
    modified=[]
    for parent,dirs,files in os.walk(folder,followlinks=False):
        dirs[:]=[d for d in dirs if not d.startswith('.') and not (Path(parent)/d).is_symlink()]
        for name in files:
            path=Path(parent)/name
            if name.startswith('.') or name=='metadata.json' or path.is_symlink():
                continue
            if path.is_file():
                modified.append(path.stat().st_mtime)
    return datetime.fromtimestamp(max(modified,default=folder.stat().st_mtime),timezone.utc)


def catalog():
    entries=[]
    for folder in sorted(ROOT.iterdir()):
        if not folder.is_dir() or folder.is_symlink() or folder.name.startswith('.'):
            continue
        meta={}
        metadata=folder/'metadata.json'
        if metadata.is_file() and not metadata.is_symlink():
            try: meta=json.loads(metadata.read_text())
            except (ValueError,OSError): pass
        files=[]
        for path in sorted(folder.iterdir(), key=lambda p: ({'.html':0,'.pdf':1,'.pptx':2}.get(p.suffix.lower(),3),p.name)):
            if path.is_file() and not path.is_symlink() and path.suffix.lower() in ['.html','.pptx','.pdf']:
                files.append({'name':path.name,'format':path.suffix[1:].upper(),
                    'url':url_for('deck',name=folder.name,filename=path.name),
                    'preview_url':url_for('viewer',name=folder.name,filename=path.name) if path.suffix.lower()=='.pptx' else None,
                    'size':round(path.stat().st_size/1024)})
        if files:
            format_files={}
            configured=meta.get('formats',{})
            for kind in ('html','pptx','pdf'):
                candidates=[f['name'] for f in files if f['format']==kind.upper()]
                selected=configured.get(kind)
                if selected in candidates:
                    format_files[kind]=selected
                elif selected is None and len(candidates)==1:
                    format_files[kind]=candidates[0]
            updated=deck_modified(folder)
            entries.append({'name':folder.name,'title':meta.get('title',folder.name.replace('-',' ').title()),
                'description':meta.get('description',''),'files':files,'format_files':format_files,
                'linked_formats':bool(format_files.get('html') and format_files.get('pptx')),
                'updated_iso':updated.isoformat().replace('+00:00','Z'),
                'updated_label':updated.strftime('%d %b %Y, %H:%M UTC')})
    return entries


@app.get('/')
def index():
    entries=catalog()
    with db() as conn:
        preferences={row[0]:row[1:] for row in conn.execute('SELECT deck,favorite,pinned FROM deck_preferences')}
    for entry in entries:
        entry['favorite'],entry['pinned']=preferences.get(entry['name'],(0,0))
    return render_template('index.html', entries=entries, count=len(entries))


@app.post('/preferences/<name>')
def deck_preference(name):
    require_csrf()
    if name not in {entry['name'] for entry in catalog()}:
        abort(404)
    field=request.form.get('field')
    value=request.form.get('value')
    if field not in ('favorite','pinned') or value not in ('0','1'):
        abort(400)
    with db() as conn:
        # The column is allowlisted above; an explicit value makes retries idempotent.
        conn.execute(f'INSERT INTO deck_preferences (deck,{field}) VALUES (?,?) '
                     f'ON CONFLICT(deck) DO UPDATE SET {field}=excluded.{field}',(name,int(value)))
    return {field:bool(int(value))}


@app.get('/decks/<name>/')
def deck_index(name):
    return deck(name,'index.html')


@app.get('/decks/<name>/<path:filename>')
def deck(name,filename):
    if '/' in name or name in ('.','..'):
        abort(404)
    path=safe_file(name+'/'+filename)
    if not path.is_file():
        abort(404)
    if path.suffix.lower()=='.html' and request.args.get('embedded')!='1':
        return redirect(url_for('viewer',name=name,filename=filename))
    return presentation_file(path)


@app.get('/healthz')
def health():
    return {'status':'ok'}


def require_csrf():
    if not hmac.compare_digest(request.form.get('csrf',''), session.get('csrf','!')):
        abort(400)


def share_rows():
    titles={e['name']:e['title'] for e in catalog()}
    with db() as conn:
        rows=conn.execute('SELECT id,deck,created,expires,revoked FROM shares ORDER BY id DESC').fetchall()
    now=time.time()
    return [{'id':r[0],'deck':r[1],'title':titles.get(r[1],r[1].replace('-',' ').title()),
        'created':time.strftime('%Y-%m-%d %H:%M UTC',time.gmtime(r[2])),
        'created_iso':datetime.fromtimestamp(r[2],timezone.utc).isoformat(),
        'expires_iso':datetime.fromtimestamp(r[3],timezone.utc).isoformat() if r[3] else '',
        'expires':time.strftime('%Y-%m-%d %H:%M UTC',time.gmtime(r[3])) if r[3] else 'No expiry',
        'active':not r[4] and (not r[3] or r[3]>now),
        'status':'Revoked' if r[4] else 'Expired' if r[3] and r[3]<=now else 'Active'} for r in rows]


@app.route('/shares', methods=['GET','POST'])
def shares():
    link=None
    if request.method=='POST':
        require_csrf()
        name=request.form.get('deck','')
        if name not in {e['name'] for e in catalog()}:
            abort(404)
        days=request.form.get('days','7')
        if days not in ('1','7','30','0'):
            abort(400)
        now=time.time()
        seed=token_hash(secrets.token_urlsafe(32))
        with db() as conn:
            result=conn.execute('INSERT INTO shares (token,deck,created,expires,copy_seed) VALUES (?,?,?,?,?)',
                (seed,name,now,now+int(days)*86400 if days!='0' else None,seed))
            token=reusable_share_token(result.lastrowid,seed)
            conn.execute('UPDATE shares SET token=?,copy_token_hash=? WHERE id=?',
                (token_hash(token),token_hash(token),result.lastrowid))
        link=PUBLIC_ORIGIN+url_for('shared',token=token)
    return render_template('shares.html', rows=share_rows(), link=link)


@app.post('/shares/<int:share_id>/revoke')
def revoke_share(share_id):
    require_csrf()
    with db() as conn:
        result=conn.execute('UPDATE shares SET revoked=1 WHERE id=?',(share_id,))
        if result.rowcount!=1:
            abort(404)
    return redirect('/shares')


def resolve_share(token):
    if len(token)!=43 or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' for c in token):
        abort(404)
    with db() as conn:
        row=conn.execute('SELECT deck FROM shares WHERE (token=? OR copy_token_hash=?) AND revoked=0 AND (expires IS NULL OR expires>?)',
            (token_hash(token),token_hash(token),time.time())).fetchone()
    if not row:
        abort(404)
    # Deck names come from authenticated creation, still validate on every access.
    name=row[0]
    folder=safe_file(name)
    if not folder.is_dir():
        abort(404)
    return name


@app.get('/s/<token>/', strict_slashes=False)
def shared(token):
    name=resolve_share(token)
    entry=next((e for e in catalog() if e['name']==name),None)
    if not entry:
        abort(404)
    if any(f['name']=='index.html' for f in entry['files']):
        return redirect(url_for('shared_file',token=token,filename='index.html'))
    pptx_files=[f for f in entry['files'] if f['format']=='PPTX']
    if len(pptx_files)==1:
        return redirect(url_for('shared_pptx',token=token,filename=pptx_files[0]['name']))
    for f in entry['files']:
        f['url']=url_for('shared_file',token=token,filename=f['name'])
        f['preview_url']=url_for('shared_pptx',token=token,filename=f['name']) if f['format']=='PPTX' else None
    return render_template('shared.html', entry=entry)


@app.get('/s/<token>/<path:filename>')
def shared_file(token,filename):
    name=resolve_share(token)
    path=safe_file(name+'/'+filename)
    if not path.is_file():
        abort(404)
    if path.suffix.lower()=='.html' and request.args.get('embedded')!='1':
        entry=next((e for e in catalog() if e['name']==name),None)
        if entry and linked_formats(entry,filename,token):
            return redirect(url_for('shared_viewer',token=token,filename=filename))
    return presentation_file(path)


@app.get('/view/<name>/<path:filename>')
def viewer(name,filename):
    path=safe_file(name+'/'+filename)
    if not path.is_file() or path.suffix.lower() not in ('.html','.pptx'):
        abort(404)
    entry=next((e for e in catalog() if e['name']==name),None)
    if not entry:
        abort(404)
    return deck_view(entry,filename)


@app.post('/shares/bulk')
def bulk_shares():
    require_csrf()
    action=request.form.get('action','')
    if action not in ('revoke','delete'):
        abort(400)
    raw=request.form.getlist('ids')
    if not raw or len(raw)>1000 or any(not n.isascii() or not n.isdigit() or len(n)>12 for n in raw):
        abort(400)
    ids=sorted({int(n) for n in raw})
    if any(n<1 for n in ids):
        abort(400)
    slots=','.join('?' for _ in ids)
    now=time.time()
    with db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        rows=conn.execute(f'SELECT id,revoked,expires FROM shares WHERE id IN ({slots})',ids).fetchall()
        if len(rows)!=len(ids):
            abort(404)
        if action=='delete':
            # Remove inactive history only; active links must first be revoked.
            if any(not r[1] and (r[2] is None or r[2]>now) for r in rows):
                abort(409,description='Revoke active links before deleting them.')
            count=conn.execute(f'DELETE FROM shares WHERE id IN ({slots})',ids).rowcount
        else:
            count=conn.execute(f'UPDATE shares SET revoked=1 WHERE id IN ({slots}) AND revoked=0 AND (expires IS NULL OR expires>?)',ids+[now]).rowcount
    return redirect(url_for('shares',done=action,count=count))


@app.get('/assets/slide-navigation.js')
def slide_navigation():
    # Public code only; thumbnails remain subject to private/deck-token access.
    return send_file(Path(__file__).parent/'static/slide-navigation.js',mimetype='application/javascript')


def presentation_file(path):
    if path.suffix.lower()!='.html':
        return send_file(path,as_attachment=path.suffix.lower()=='.pptx',conditional=True)
    raw=path.read_bytes()
    html=raw.decode('utf-8')
    # This adapter targets the canvas-based HyperDrive decks. Other deck types keep their player.
    if 'const slides = []' in html and 'function go(' in html and 'function fit(' in html:
        version=hashlib.sha256(raw).hexdigest()
        manifest=path.parent/'navigation'/'thumbnails.json'
        thumbnails=False
        if manifest.is_file() and not manifest.is_symlink():
            try: thumbnails=json.loads(manifest.read_text()).get('source_sha256')==version
            except (OSError,ValueError): pass
        script='<script src="'+url_for('slide_navigation')+'" data-thumbnails="'+('yes' if thumbnails else 'no')+'" data-version="'+version+'"></script>'
        if '</body>' in html:
            html=html.rsplit('</body>',1)[0]+script+'</body>'+html.rsplit('</body>',1)[1]
        else:
            html+=script
    return Response(html,mimetype='text/html')


def pptx_source(name,filename):
    path=safe_file(name+'/'+filename)
    if not path.is_file() or path.suffix.lower()!='.pptx':
        abort(404)
    return path


def pptx_page(name,filename,token=None):
    pptx_source(name,filename)
    entry=next((e for e in catalog() if e['name']==name),None)
    if not entry:abort(404)
    if token:
        manifest=url_for('shared_pptx_data',token=token,filename=filename,asset='manifest')
        download=url_for('shared_file',token=token,filename=filename)
    else:
        manifest=url_for('pptx_data',name=name,filename=filename,asset='manifest')
        download=url_for('deck',name=name,filename=filename)
    return render_template('pptx.html',title=entry['title'],manifest=manifest,download=download)


@app.get('/pptx/<name>/<path:filename>')
def pptx_player(name,filename):
    return pptx_page(name,filename)


@app.get('/s/<token>/_pptx/<path:filename>')
def shared_pptx(token,filename):
    name=resolve_share(token)
    pptx_source(name,filename)
    if request.args.get('embedded')!='1':
        entry=next((e for e in catalog() if e['name']==name),None)
        if entry and linked_formats(entry,filename,token):
            return redirect(url_for('shared_viewer',token=token,filename=filename))
    return pptx_page(name,filename,token)


def pptx_asset(name,filename,asset):
    path=pptx_source(name,filename)
    result=pptx_preview.status(path)
    if asset=='manifest':
        return result,202 if result['status']=='processing' else 200
    if result['status']!='ready':abort(404)
    if asset=='document.pdf':
        return send_file(pptx_preview.cache_dir(path)/asset,mimetype='application/pdf')
    import re
    match=re.fullmatch(r'page-(\d+)\.jpg',asset)
    if not match or not 1<=int(match.group(1))<=result['pages']:abort(404)
    return send_file(pptx_preview.cache_dir(path)/f'page-{int(match.group(1))}.jpg',mimetype='image/jpeg')


@app.get('/pptx-data/<name>/<path:filename>/<asset>')
def pptx_data(name,filename,asset):
    return pptx_asset(name,filename,asset)


@app.get('/s/<token>/_pptx-data/<path:filename>/<asset>')
def shared_pptx_data(token,filename,asset):
    return pptx_asset(resolve_share(token),filename,asset)


def linked_formats(entry,filename,token=None):
    files=entry['format_files']
    if not entry['linked_formats'] or filename not in files.values():
        return {}
    def view(file):
        return url_for('shared_viewer',token=token,filename=file) if token else url_for('viewer',name=entry['name'],filename=file)
    return {'html':view(files['html']),'pptx':view(files['pptx']),
        'download_pptx':url_for('shared_file',token=token,filename=files['pptx']) if token else url_for('deck',name=entry['name'],filename=files['pptx'])}


def deck_view(entry,filename,token=None):
    name=entry['name']
    if token:
        source=url_for('shared_pptx',token=token,filename=filename,embedded='1') if filename.lower().endswith('.pptx') else url_for('shared_file',token=token,filename=filename,embedded='1')
    else:
        source=url_for('pptx_player',name=name,filename=filename) if filename.lower().endswith('.pptx') else url_for('deck',name=name,filename=filename,embedded='1')
    return render_template('viewer.html',title=entry['title'],source=source,formats=linked_formats(entry,filename,token),active_format='pptx' if filename.lower().endswith('.pptx') else 'html',shared=bool(token))


@app.get('/s/<token>/_view/<path:filename>')
def shared_viewer(token,filename):
    name=resolve_share(token)
    path=safe_file(name+'/'+filename)
    if not path.is_file() or path.suffix.lower() not in ('.html','.pptx'):
        abort(404)
    entry=next((e for e in catalog() if e['name']==name),None)
    if not entry:abort(404)
    return deck_view(entry,filename,token)


def reusable_share_token(share_id,seed):
    secret=CONFIG.get('share_copy_secret')
    if not secret:
        abort(503,description='Share-link copying is unavailable.')
    digest=hmac.new(secret.encode(),f'slides-share-v1:{share_id}:{seed}'.encode(),hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip('=')


@app.post('/shares/<int:share_id>/copy')
def copy_share(share_id):
    require_csrf()
    with db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute('SELECT token,copy_seed,expires,revoked FROM shares WHERE id=?',(share_id,)).fetchone()
        if not row:abort(404)
        if row[3] or (row[2] is not None and row[2]<=time.time()):
            abort(410,description='This share link is no longer active.')
        seed=row[1] or row[0]
        token=reusable_share_token(share_id,seed)
        conn.execute('UPDATE shares SET copy_seed=?,copy_token_hash=? WHERE id=?',(seed,token_hash(token),share_id))
    return {'url':PUBLIC_ORIGIN+url_for('shared',token=token)}


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(410)
@app.errorhandler(500)
@app.errorhandler(502)
@app.errorhandler(503)
@app.errorhandler(504)
def friendly_error(error):
    code=error.code
    if code in (500,502,503,504):
        heading='Slides is temporarily unavailable'
        message='We could not open this page right now.'
        detail='Please try again in a moment.'
    elif request.path=='/s' or request.path.startswith('/s/') or code==410:
        heading='Link unavailable'
        message='This link may be incorrect, expired, or no longer shared.'
        detail='Check the address, or ask the person who sent it for a new link.'
    elif code==403:
        heading='Unable to open this page'
        message='You do not have access to this page.'
        detail='Sign in to the library, or ask the sender for a new share link.'
    elif code==400:
        heading='This request could not be completed'
        message='Please refresh the page and try again.'
        detail='If you were signing in, open the login page again.'
    else:
        heading='Page not found'
        message='This page may have moved, or the address may be incorrect.'
        detail='Check the address, or return to the slide library.'
    return render_template('error.html',heading=heading,message=message,detail=detail,error_code=code),code
