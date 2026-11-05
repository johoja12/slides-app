"""Bounded ingestion and immutable revision storage. Never writes to library originals."""
import hashlib
from datetime import datetime, timezone
import json
import os
import posixpath
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import time
import uuid
import zipfile
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

MAX_BYTES = 100 * 1024 * 1024
MAX_EXPANDED = 300 * 1024 * 1024
MAX_FILES = 1500
MAX_FILE = 100 * 1024 * 1024


class InvalidBundle(ValueError):
    pass


def schema(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS decks (id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, current_revision INTEGER)')
    conn.execute('CREATE TABLE IF NOT EXISTS revisions (id INTEGER PRIMARY KEY, deck_id TEXT NOT NULL, created REAL NOT NULL, modified REAL NOT NULL, digest TEXT NOT NULL, manifest TEXT NOT NULL, UNIQUE(deck_id,digest))')
    conn.execute('CREATE TABLE IF NOT EXISTS deck_tags (deck TEXT NOT NULL, tag TEXT NOT NULL, PRIMARY KEY(deck,tag))')
    conn.execute('CREATE TABLE IF NOT EXISTS presenter_notes (deck TEXT NOT NULL, revision TEXT NOT NULL, filename TEXT NOT NULL, notes TEXT NOT NULL, PRIMARY KEY(deck,revision,filename))')
    conn.execute('CREATE TABLE IF NOT EXISTS share_activity (share_id INTEGER PRIMARY KEY, views INTEGER NOT NULL DEFAULT 0, last_opened REAL)')
    conn.execute('CREATE TABLE IF NOT EXISTS share_visits (share_id INTEGER NOT NULL, visitor TEXT NOT NULL, stamp REAL NOT NULL, PRIMARY KEY(share_id,visitor))')
    columns = {row[1] for row in conn.execute('PRAGMA table_info(shares)')}
    if 'revision_id' not in columns:
        conn.execute('BEGIN IMMEDIATE')
        if 'revision_id' not in {row[1] for row in conn.execute('PRAGMA table_info(shares)')}:
            conn.execute('ALTER TABLE shares ADD COLUMN revision_id INTEGER')
        conn.commit()
    conn.execute('CREATE VIRTUAL TABLE IF NOT EXISTS slide_search USING fts5(deck UNINDEXED, revision UNINDEXED, filename UNINDEXED, page UNINDEXED, content, tokenize="unicode61")')
    conn.execute('CREATE TABLE IF NOT EXISTS search_sources (deck TEXT NOT NULL, filename TEXT NOT NULL, signature TEXT NOT NULL, PRIMARY KEY(deck,filename))')


def path_name(value):
    if not value or len(value) > 240 or '\\' in value or any(ord(c) < 32 for c in value):
        raise InvalidBundle('Use ordinary relative filenames without control characters.')
    parts = PurePosixPath(value).parts
    if not parts or value.startswith('/') or any(p in ('.', '..') or p.startswith('.') or ':' in p for p in parts):
        raise InvalidBundle('Hidden, absolute and parent-directory paths are not allowed.')
    return '/'.join(parts)


def visible_files(folder):
    total = 0
    count = 0
    for parent, dirs, files in os.walk(folder, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and not (Path(parent) / d).is_symlink())
        for name in sorted(files):
            source = Path(parent) / name
            if name.startswith('.') or source.is_symlink() or not source.is_file():
                continue
            relative = path_name(source.relative_to(folder).as_posix())
            size = source.stat().st_size
            total += size
            count += 1
            if count > MAX_FILES or total > MAX_EXPANDED or size > MAX_FILE:
                raise InvalidBundle('Bundle exceeds the file count or expanded size limit.')
            yield relative, source


def digest_folder(folder):
    digest = hashlib.sha256()
    manifest = []
    for relative, source in visible_files(folder):
        data = source.read_bytes()
        digest.update(relative.encode() + b'\0' + hashlib.sha256(data).digest())
        manifest.append({'name': relative, 'bytes': len(data)})
    return digest.hexdigest(), manifest


def snapshot(conn, state, name, folder, modified, expected=None, select=False):
    """Caller holds BEGIN IMMEDIATE. Stage privately; publish before database commit."""
    row = conn.execute('SELECT id,current_revision FROM decks WHERE name=?', (name,)).fetchone()
    if not row:
        row = (uuid.uuid4().hex, None)
        conn.execute('INSERT INTO decks(id,name) VALUES (?,?)', (row[0], name))
    if expected is not None and str(row[1] or 'live') != expected:
        raise InvalidBundle('The current version changed. Reload before publishing.')
    storage = state / 'revisions'
    storage.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='stage-', dir=storage) as stage:
        stage = Path(stage)
        for relative, source in visible_files(folder):
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        digest, manifest = digest_folder(stage)
        # Fail if the source changed while copying; no mixed revision is published.
        if digest_folder(folder)[0] != digest:
            raise InvalidBundle('Files changed while copying. Try again.')
        existing = conn.execute('SELECT id FROM revisions WHERE deck_id=? AND digest=?', (row[0], digest)).fetchone()
        if existing:
            revision = existing[0]
        else:
            revision = conn.execute('INSERT INTO revisions(deck_id,created,modified,digest,manifest) VALUES (?,?,?,?,?)',
                (row[0], time.time(), modified, digest, json.dumps(manifest))).lastrowid
            destination = storage / str(revision)
            if destination.exists():
                # A failed transaction can leave an unreferenced immutable directory.
                # Never reuse its bytes; move it aside before publishing.
                destination.rename(storage / ('orphan-' + uuid.uuid4().hex))
            stage.rename(destination)
            stage.mkdir()
        if select:
            conn.execute('UPDATE decks SET current_revision=? WHERE id=?', (revision, row[0]))
        return revision


class AssetReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if value and (key in ('src', 'poster') or (tag == 'link' and key == 'href')):
                self.references.append(value)
            if value and key == 'srcset':
                self.references.extend(item.strip().split()[0] for item in value.split(',') if item.strip())


def validate(folder, formats):
    files = dict(visible_files(folder))
    presentations = [name for name in files if '/' not in name and Path(name).suffix.lower() in ('.html', '.pdf', '.pptx')]
    if not presentations:
        raise InvalidBundle('Add at least one top-level HTML, PPTX or PDF presentation.')
    for name, source in files.items():
        suffix = source.suffix.lower()
        if suffix in ('.exe', '.sh', '.bat', '.ps1', '.php', '.py', '.env'):
            raise InvalidBundle('Executable server files are not accepted.')
        if suffix == '.pdf':
            with source.open('rb') as pdf:
                if not pdf.read(1024).lstrip().startswith(b'%PDF-'):
                    raise InvalidBundle('A PDF has an invalid file signature.')
        if suffix == '.pptx':
            try:
                with zipfile.ZipFile(source) as archive:
                    entries = archive.infolist()
                    if len(entries) > MAX_FILES * 10 or sum(i.file_size for i in entries) > MAX_EXPANDED or 'ppt/presentation.xml' not in archive.namelist():
                        raise InvalidBundle('Invalid or oversized PowerPoint.')
                    for item in entries:
                        if item.filename.startswith('/') or '\\' in item.filename or '..' in PurePosixPath(item.filename).parts or stat.S_ISLNK(item.external_attr >> 16):
                            raise InvalidBundle('Unsafe PowerPoint package member.')
                        if item.file_size > MAX_FILE or 'vbaProject' in item.filename or 'embeddings/' in item.filename:
                            raise InvalidBundle('Macros and embedded objects are not accepted.')
                        if item.filename.endswith('.rels'):
                            document = ET.fromstring(archive.read(item))
                            if any(e.get('TargetMode') == 'External' and not e.get('Type', '').endswith('/hyperlink') for e in document):
                                raise InvalidBundle('PowerPoint external resource relationships are not accepted.')
            except (zipfile.BadZipFile, ET.ParseError, RuntimeError):
                raise InvalidBundle('The PowerPoint package is malformed.') from None
        if suffix == '.html':
            if source.stat().st_size > 8 * 1024 * 1024:
                raise InvalidBundle('An HTML document exceeds 8 MB.')
            parser = AssetReferences()
            try:
                parser.feed(source.read_text(encoding='utf-8'))
            except UnicodeError:
                raise InvalidBundle('HTML documents must use UTF-8.') from None
            for reference in parser.references:
                parsed = urlsplit(reference)
                if parsed.scheme in ('https', 'http', 'data') or reference.startswith('#'):
                    continue
                if parsed.scheme or parsed.netloc:
                    raise InvalidBundle('HTML contains an unsupported resource URL.')
                relative = unquote(parsed.path)
                if not relative:
                    continue
                if relative.startswith('/') or '\\' in relative:
                    raise InvalidBundle('HTML resources must use relative paths.')
                candidate = path_name(posixpath.normpath(posixpath.join(posixpath.dirname(name),relative)))
                if candidate not in files:
                    raise InvalidBundle('An HTML relative resource is missing from the bundle.')
    for kind, filename in formats.items():
        if kind not in ('html', 'pdf', 'pptx') or filename not in presentations or Path(filename).suffix.lower() != '.' + kind:
            raise InvalidBundle('Choose an existing matching file for each paired format.')
    for kind in ('html', 'pdf', 'pptx'):
        candidates = [name for name in presentations if Path(name).suffix.lower() == '.' + kind]
        if len(candidates) > 1 and kind not in formats:
            raise InvalidBundle('Choose an explicit paired file when a format has multiple candidates.')
        if len(candidates) == 1:
            formats.setdefault(kind, candidates[0])
    return formats


def unpack(uploads, folder, timestamps=None):
    total = 0
    uploaded = 0
    count = 0
    for upload in uploads:
        name = path_name(upload.filename or '')
        if '/' in name:
            raise InvalidBundle('Upload flat files or a ZIP containing relative assets.')
        target = folder / name
        if target.exists():
            raise InvalidBundle('Duplicate filenames are not accepted.')
        with target.open('xb') as output:
            while chunk := upload.stream.read(1024 * 1024):
                uploaded += len(chunk)
                if uploaded > MAX_BYTES:
                    raise InvalidBundle('Uploads are limited to 100 MB in total.')
                output.write(chunk)
        if target.suffix.lower() != '.zip':
            stamp=(timestamps or {}).get(name)
            if stamp is not None:
                if not isinstance(stamp,(int,float)) or not 0<=stamp<=time.time()+86400:
                    raise InvalidBundle('Invalid source modification date.')
                os.utime(target,(stamp,stamp))
            count += 1
            total += target.stat().st_size
            if total > MAX_EXPANDED:
                raise InvalidBundle('The expanded bundle exceeds 300 MB.')
            continue
        try:
            with zipfile.ZipFile(target) as archive:
                for entry in archive.infolist():
                    normalized = path_name(entry.filename.rstrip('/'))
                    mode = entry.external_attr >> 16
                    if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)) or entry.flag_bits & 1:
                        raise InvalidBundle('Links, special files and encrypted archives are not accepted.')
                    if entry.is_dir():
                        continue
                    count += 1
                    if count > MAX_FILES or entry.file_size > MAX_FILE:
                        raise InvalidBundle('Too many files or an oversized archive member.')
                    destination = folder / normalized
                    if destination.exists():
                        raise InvalidBundle('The bundle contains conflicting filenames.')
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(entry) as source, destination.open('xb') as output:
                        expanded = 0
                        while chunk := source.read(1024 * 1024):
                            expanded += len(chunk)
                            total += len(chunk)
                            if expanded > MAX_FILE or total > MAX_EXPANDED:
                                raise InvalidBundle('The expanded bundle exceeds 300 MB.')
                            output.write(chunk)
                    try:
                        stamp=datetime(*entry.date_time,tzinfo=timezone.utc).timestamp()
                        if 0<=stamp<=time.time()+86400:os.utime(destination,(stamp,stamp))
                    except (ValueError,OverflowError):
                        pass
        except (zipfile.BadZipFile, RuntimeError, OSError):
            raise InvalidBundle('Could not read this ZIP bundle.') from None
        target.unlink()
    if count > MAX_FILES:
        raise InvalidBundle('Too many uploaded files.')
