"""Authenticated organization, revision, ingestion, search and presenter features."""
from datetime import datetime, timezone
import hashlib
import json
import re
import secrets
import tempfile
import time
import unicodedata
from pathlib import Path
from types import SimpleNamespace

from flask import Response, abort, g, redirect, request, send_file, session, url_for
import library_store as store
import slide_content


def register(namespace):
    h = SimpleNamespace(**namespace)
    app = h.app

    def entries():
        values=h.catalog()
        enrich_index(values)
        return {entry['name']: entry for entry in values}

    def entry(name):
        value = entries().get(name)
        if value is None:
            abort(404)
        return value

    def current(conn, name):
        row = conn.execute('SELECT current_revision FROM decks WHERE name=?', (name,)).fetchone()
        return str(row[0]) if row and row[0] else 'live'

    def checkpoint(name, select=False, source_revision=None):
        if source_revision:
            h.revision_folder(name, source_revision)
            return int(source_revision)
        folder = h.deck_folder(name)
        modified = h.deck_modified(folder).timestamp()
        try:
            with h.db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                return store.snapshot(conn, h.STATE, name, folder, modified, select=select)
        except store.InvalidBundle as error:
            abort(422, description=str(error))

    def enrich_index(values):
        with h.db() as conn:
            tags = {}
            for name, tag in conn.execute('SELECT deck,tag FROM deck_tags ORDER BY tag'):
                tags.setdefault(name, []).append(tag)
            revisions = {name: revision for name, revision in conn.execute('SELECT name,current_revision FROM decks')}
        for value in values:
            value['tags'] = tags.get(value['name'], [])
            value['revision'] = revisions.get(value['name'])
            source = value['format_files'].get('html') or value['format_files'].get('pptx') or value['format_files'].get('pdf') or value['files'][0]['name']
            value['thumbnail'] = url_for('thumbnail', name=value['name'], filename=source)
        return sorted({tag for value in values for tag in value['tags']})

    def normalize_tag(value):
        tag = ' '.join(unicodedata.normalize('NFKC', value).casefold().split())
        if not tag or len(tag) > 48 or any(ord(c) < 32 for c in tag) or ',' in tag:
            abort(422, description='Tags must contain 1–48 characters without commas or control characters.')
        return tag

    @app.post('/tags/<name>')
    def deck_tags(name):
        h.require_csrf()
        entry(name)
        raw = request.form.get('tags', '')
        tags = {normalize_tag(value) for value in raw.split(',') if value.strip()}
        if len(tags) > 20:
            abort(422, description='Use at most 20 tags per deck.')
        with h.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('DELETE FROM deck_tags WHERE deck=?', (name,))
            conn.executemany('INSERT INTO deck_tags(deck,tag) VALUES (?,?)', ((name, tag) for tag in tags))
        return {'tags': sorted(tags)}

    @app.post('/tags')
    def manage_tags():
        h.require_csrf()
        action = request.form.get('action')
        old = normalize_tag(request.form.get('tag', ''))
        if action not in ('rename', 'delete'):
            abort(400)
        new = normalize_tag(request.form.get('replacement', '')) if action == 'rename' else None
        with h.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if new:
                conn.execute('INSERT OR IGNORE INTO deck_tags(deck,tag) SELECT deck,? FROM deck_tags WHERE tag=?', (new, old))
            if old != new:
                conn.execute('DELETE FROM deck_tags WHERE tag=?', (old,))
        return redirect('/')

    def thumb(name, filename):
        path = h.safe_file(name + '/' + filename)
        if not path.is_file() or path.suffix.lower() not in ('.html', '.pptx', '.pdf'):
            abort(404)
        data, mimetype, status = slide_content.thumbnail(path, h.STATE)
        response = send_file(data, mimetype=mimetype) if isinstance(data, Path) else Response(data, mimetype=mimetype)
        response.headers['X-Preview-State'] = status
        return response

    @app.get('/thumbnail/<name>/<path:filename>', endpoint='thumbnail')
    @app.get('/r/<int:revision>/thumbnail/<name>/<path:filename>', endpoint='thumbnail')
    def thumbnail(name, filename, revision=None):
        return thumb(name, filename)

    @app.get('/s/<token>/_thumbnail/<path:filename>', endpoint='shared_thumbnail')
    def shared_thumbnail(token, filename):
        return thumb(h.resolve_share(token), filename)

    @app.route('/history/<name>', methods=['GET', 'POST'])
    def history(name):
        value = entry(name)
        if request.method == 'POST':
            h.require_csrf()
            if request.form.get('action') == 'snapshot':
                checkpoint(name)
            elif request.form.get('action') == 'select':
                selected = request.form.get('revision', '')
                if selected != 'live':
                    if not selected.isascii() or not selected.isdigit():
                        abort(400)
                    h.revision_folder(name, int(selected))
                elif not (h.ROOT / name).is_dir() or (h.ROOT / name).is_symlink():
                    abort(404)
                with h.db() as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    if request.form.get('expected') != current(conn, name):
                        abort(409, description='Another window changed the current revision. Reload before restoring.')
                    conn.execute('UPDATE decks SET current_revision=? WHERE name=?', (None if selected == 'live' else int(selected), name))
            else:
                abort(400)
            return redirect(url_for('history', name=name))
        with h.db() as conn:
            rows = conn.execute('SELECT r.id,r.created,r.modified,r.manifest FROM revisions r JOIN decks d ON d.id=r.deck_id WHERE d.name=? ORDER BY r.id DESC', (name,)).fetchall()
            selected = current(conn, name)
        revisions = []
        for rid, created, modified, manifest in rows:
            files = json.loads(manifest)
            for file in files:
                file['url'] = url_for('deck', name=name, revision=rid, filename=file['name'])
            revisions.append(dict(id=rid, created=datetime.fromtimestamp(created, timezone.utc).isoformat(), modified=datetime.fromtimestamp(modified, timezone.utc).isoformat(), files=files))
        return h.ui_page('history', entry=value, revisions=revisions, selected=selected, live=(h.ROOT/name).is_dir())

    @app.route('/upload', methods=['GET', 'POST'])
    def upload():
        values = entries()
        if request.method == 'GET':
            return h.ui_page('upload', entries=list(values.values()),deck=request.args.get('deck',''))
        h.require_csrf()
        name = request.form.get('name', '')
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', name):
            return {'error': 'Use a deck name of 1–80 lowercase letters, digits or hyphens.'}, 422
        if request.form.get('mode') not in ('new','revision'):
            return {'error':'Choose a new deck or a new revision.'},400
        replacing = request.form.get('mode') == 'revision'
        if (name in values) != replacing:
            return {'error': 'That deck already exists. Choose “New revision”, or use a new name.' if name in values else 'The deck to revise no longer exists.'}, 409
        uploads = request.files.getlist('files')
        if not uploads or len(uploads) > 50:
            return {'error': 'Choose 1–50 files or ZIP bundles.'}, 422
        h.STATE.mkdir(parents=True, exist_ok=True)
        ingestion = h.STATE/'ingestion'
        ingestion.mkdir(exist_ok=True)
        # Across all workers, bound concurrent upload staging with a kernel lock.
        import fcntl
        with (ingestion/'lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {'error': 'Another upload is publishing. Try again shortly.'}, 409
            try:
                # The exclusive lock proves no publisher owns abandoned staging folders.
                import shutil
                for abandoned in ingestion.glob('upload-*'):
                    if abandoned.is_dir() and not abandoned.is_symlink():
                        shutil.rmtree(abandoned)
                with tempfile.TemporaryDirectory(prefix='upload-', dir=ingestion) as stage:
                    folder = Path(stage)
                    timestamps=json.loads(request.form.get('last_modified','{}'))
                    if not isinstance(timestamps,dict):
                        raise store.InvalidBundle('Invalid source modification dates.')
                    store.unpack(uploads, folder, timestamps)
                    formats = {kind: request.form.get(kind, '').strip() for kind in ('html','pptx','pdf') if request.form.get(kind, '').strip()}
                    formats = store.validate(folder, formats)
                    # Metadata is authored by the application, never taken on trust from an archive.
                    (folder/'metadata.json').write_text(json.dumps({'title': request.form.get('title','').strip()[:200] or name.replace('-',' ').title(), 'formats': formats}))
                    with h.db() as conn:
                        conn.execute('BEGIN IMMEDIATE')
                        existing = conn.execute('SELECT id,current_revision FROM decks WHERE name=?',(name,)).fetchone()
                        if not replacing and (existing or name in entries()):
                            abort(409, description='This deck name was just taken. Reload before publishing.')
                        if replacing and request.form.get('expected') != current(conn, name):
                            abort(409, description='The current revision changed. Reload before publishing.')
                        if replacing and (not existing or existing[1] is None):
                            original = h.deck_folder(name)
                            store.snapshot(conn, h.STATE, name, original, h.deck_modified(original).timestamp())
                        rid = store.snapshot(conn, h.STATE, name, folder, h.deck_modified(folder).timestamp(), select=True)
                return {'url': url_for('history', name=name), 'revision': rid}
            except (store.InvalidBundle, OSError, ValueError) as error:
                message = str(error) if isinstance(error, store.InvalidBundle) else 'The upload could not be published. Check filenames and available storage.'
                return {'error': message}, 422

    def observe_share(share_id):
        # Explicit entry navigation only; no asset/reload inflation within 30 minutes.
        if request.method != 'GET' or request.headers.get('Purpose') == 'prefetch' or request.headers.get('Sec-Purpose','').startswith('prefetch'):
            return
        agent = request.headers.get('User-Agent', '').lower()
        if not agent or any(word in agent for word in ('bot','spider','crawler','preview','headless')):
            return
        visitors = session.get('share_observers', {})
        key = str(share_id)
        visitor = visitors.get(key)
        if not visitor:
            visitor = secrets.token_urlsafe(24)
            visitors = dict(list(visitors.items())[-19:])
            visitors[key] = visitor
            session['share_observers'] = visitors
        now = time.time()
        with h.db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('DELETE FROM share_visits WHERE stamp<?', (now-1800,))
            row = conn.execute('SELECT stamp FROM share_visits WHERE share_id=? AND visitor=?', (share_id,h.token_hash(visitor))).fetchone()
            if row:
                return
            conn.execute('INSERT OR REPLACE INTO share_visits VALUES (?,?,?)',(share_id,h.token_hash(visitor),now))
            conn.execute('INSERT INTO share_activity(share_id,views,last_opened) VALUES (?,1,?) ON CONFLICT(share_id) DO UPDATE SET views=views+1,last_opened=excluded.last_opened',(share_id,now))

    @app.post('/shares/<int:share_id>/activity/reset')
    def reset_activity(share_id):
        h.require_csrf()
        with h.db() as conn:
            if not conn.execute('SELECT 1 FROM shares WHERE id=?',(share_id,)).fetchone():
                abort(404)
            conn.execute('DELETE FROM share_activity WHERE share_id=?',(share_id,))
            conn.execute('DELETE FROM share_visits WHERE share_id=?',(share_id,))
        return redirect('/shares')

    def sync_search(values):
        deadline = time.monotonic()+3
        pending = False
        sources = []
        with h.db() as conn:
            known = {(name,filename): signature for name,filename,signature in conn.execute('SELECT deck,filename,signature FROM search_sources')}
            revisions = {name:str(revision or 'live') for name,revision in conn.execute('SELECT name,current_revision FROM decks')}
        for value in values.values():
            folder = h.deck_folder(value['name'])
            revision = revisions.get(value['name'],'live')
            for file in value['files']:
                path = folder/file['name']
                info = path.stat()
                signature = f'{revision}:{info.st_mtime_ns}:{info.st_ctime_ns}:{info.st_size}:{info.st_ino}'
                key = (value['name'],file['name'])
                sources.append(key)
                if known.get(key) == signature:
                    continue
                # Invalidate before extraction; native parsers never hold the SQLite write lock.
                with h.db() as conn:
                    conn.execute('DELETE FROM slide_search WHERE deck=? AND filename=?',key)
                if time.monotonic() > deadline:
                    pending = True
                    continue
                pages = slide_content.extract(path)
                try:
                    after=path.stat()
                    unchanged=(info.st_mtime_ns,info.st_ctime_ns,info.st_size,info.st_ino)==(after.st_mtime_ns,after.st_ctime_ns,after.st_size,after.st_ino)
                except OSError:
                    unchanged=False
                if not unchanged:
                    pending=True
                    continue
                with h.db() as conn:
                    if current(conn,value['name'])!=revision:
                        pending=True
                        continue
                    conn.execute('DELETE FROM slide_search WHERE deck=? AND filename=?',key)
                    conn.executemany('INSERT INTO slide_search(deck,revision,filename,page,content) VALUES (?,?,?,?,?)', ((value['name'],revision,file['name'],page,text) for page,text in pages))
                    conn.execute('INSERT OR REPLACE INTO search_sources VALUES (?,?,?)',key+(signature,))
        with h.db() as conn:
            for key in known.keys()-set(sources):
                conn.execute('DELETE FROM slide_search WHERE deck=? AND filename=?',key)
                conn.execute('DELETE FROM search_sources WHERE deck=? AND filename=?',key)
        return pending

    @app.get('/search')
    def search_content():
        values = entries()
        pending = sync_search(values)
        query = request.args.get('q','').strip()[:200]
        terms = re.findall(r'\w+',query, flags=re.UNICODE)[:12]
        tags = [normalize_tag(tag) for tag in request.args.getlist('tag')][:20]
        favorites = request.args.get('favorites') == '1'
        try:
            page = max(1,min(10000,int(request.args.get('page','1'))))
        except ValueError:
            abort(400)
        results = []
        total = 0
        if terms:
            match = ' OR '.join('"'+term.replace('"','""')+'"' for term in terms)
            clauses = ['slide_search MATCH ?']
            args = [match]
            if favorites:
                clauses.append('deck IN (SELECT deck FROM deck_preferences WHERE favorite=1)')
            for tag in tags:
                clauses.append('deck IN (SELECT deck FROM deck_tags WHERE tag=?)')
                args.append(tag)
            where = ' AND '.join(clauses)
            with h.db() as conn:
                total = conn.execute('SELECT count(*) FROM slide_search WHERE '+where,args).fetchone()[0]
                rows = conn.execute('SELECT deck,revision,filename,page,snippet(slide_search,4,"",""," … ",28) FROM slide_search WHERE '+where+' ORDER BY bm25(slide_search),deck,filename,CAST(page AS INTEGER) LIMIT 20 OFFSET ?',args+[(page-1)*20]).fetchall()
            for name,revision,filename,slide,snippet in rows:
                if name in values:
                    kwargs = {} if revision=='live' else {'revision':int(revision)}
                    endpoint = 'viewer' if Path(filename).suffix.lower() in ('.html','.pptx') else 'deck'
                    results.append(dict(title=values[name]['title'],filename=filename,page=slide,snippet=snippet,url=url_for(endpoint,name=name,filename=filename,**kwargs)+('#page='+str(slide) if filename.lower().endswith('.pdf') else '#'+str(slide))))
        with h.db() as conn:
            all_tags = sorted({tag for name,tag in conn.execute('SELECT deck,tag FROM deck_tags') if name in values})
        return h.ui_page('search',query=query,results=results,total=total,page=page,pending=pending,tags=tags,all_tags=all_tags,favorites=favorites)

    @app.route('/presenter/<name>/<path:filename>', methods=['GET','POST'], endpoint='presenter')
    @app.route('/r/<int:revision>/presenter/<name>/<path:filename>', methods=['GET','POST'], endpoint='presenter')
    def presenter(name, filename, revision=None):
        value = entry(name)
        path = h.safe_file(name+'/'+filename)
        if not path.is_file() or path.suffix.lower() not in ('.html','.pptx'):
            abort(404)
        with h.db() as conn:
            identity = str(revision) if revision else current(conn,name)
            if request.method == 'POST':
                h.require_csrf()
                notes = request.form.get('notes','')
                if len(notes) > 12000:
                    abort(422,description='Notes are limited to 12,000 characters.')
                conn.execute('INSERT INTO presenter_notes VALUES (?,?,?,?) ON CONFLICT(deck,revision,filename) DO UPDATE SET notes=excluded.notes',(name,identity,filename,notes))
                return {'saved':True}
            row = conn.execute('SELECT notes FROM presenter_notes WHERE deck=? AND revision=? AND filename=?',(name,identity,filename)).fetchone()
        channel = request.args.get('channel','')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{24,80}',channel):
            channel = secrets.token_urlsafe(24)
        supported = path.suffix.lower()=='.pptx' or all(word in path.read_text(errors='replace') for word in ('const slides = []','function go(','function fit('))
        audience = url_for('viewer',name=name,filename=filename,revision=revision) if revision else url_for('viewer',name=name,filename=filename)
        source = url_for('pptx_player',name=name,filename=filename) if path.suffix.lower()=='.pptx' else url_for('deck',name=name,filename=filename,embedded='1')
        return h.ui_page('presenter',entry=value,filename=filename,notes=row[0] if row else '',channel=channel,supported=supported,audience=audience,source=source)

    namespace.update(checkpoint=checkpoint, observe_share=observe_share, enrich_index=enrich_index)
