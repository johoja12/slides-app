"""Static text extraction and bounded, script-free preview helpers."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import threading
import zipfile
import xml.etree.ElementTree as ET

import library_store
import pptx_preview

POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='pdf-preview')
PENDING = set()
LOCK = threading.Lock()


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        private = (tag in ('script', 'style', 'noscript', 'template', 'head') or 'hidden' in attrs or attrs.get('aria-hidden') == 'true'
                   or any(word in (attrs.get('class', '') + ' ' + attrs.get('id', '')).lower() for word in ('notes', 'presenter', 'speaker'))
                   or 'display:none' in attrs.get('style', '').replace(' ', '').lower())
        if tag not in ('img','br','hr','meta','link','input','source','wbr','area','base','embed','param','track','col'):
            self.stack.append((tag, private or (self.stack[-1][1] if self.stack else False)))
        if tag in ('p','div','h1','h2','h3','li','section','br'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                self.stack = self.stack[:index]
                break
        self.parts.append('\n')

    def handle_data(self, data):
        if not self.stack or not self.stack[-1][1]:
            self.parts.append(data)

    def text(self):
        return '\n'.join(' '.join(line.split()) for line in ''.join(self.parts).splitlines() if line.strip())[:2_000_000]


def extract(path):
    if path.stat().st_size > library_store.MAX_FILE:
        return []
    suffix = path.suffix.lower()
    try:
        if suffix == '.html':
            if path.stat().st_size > 8 * 1024 * 1024:
                return []
            parser = Text()
            parser.feed(path.read_text(encoding='utf-8'))
            return [(1, parser.text())]
        if suffix == '.pptx':
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > 20000 or sum(i.file_size for i in entries) > library_store.MAX_EXPANDED:
                    return []
                slides = sorted((i for i in entries if re.fullmatch(r'ppt/slides/slide\d+\.xml', i.filename)), key=lambda i: int(re.search(r'(\d+)\.xml', i.filename)[1]))[:500]
                return [(int(re.search(r'(\d+)\.xml', i.filename)[1]), ' '.join(e.text or '' for e in ET.fromstring(archive.read(i)).iter() if e.tag.endswith('}t'))[:100_000]) for i in slides if i.file_size < 2_000_000]
        if suffix == '.pdf':
            with __import__('tempfile').TemporaryDirectory(prefix='slides-text-') as work:
                output = Path(work) / 'text.txt'
                subprocess.run(['pdftotext','-f','1','-l','500','-layout',str(path),str(output)], check=True, timeout=15, capture_output=True)
                if output.stat().st_size > 8_000_000:
                    return []
                return [(i + 1, text[:100_000]) for i, text in enumerate(output.read_text(errors='replace').split('\f')) if text.strip()]
    except (OSError, ValueError, UnicodeError, zipfile.BadZipFile, ET.ParseError, subprocess.SubprocessError, RuntimeError):
        return []
    return []


def svg(lines, label='HTML · text preview'):
    import textwrap
    wrapped = []
    for line in lines:
        wrapped.extend(textwrap.wrap(line, width=46))
        if len(wrapped) >= 5:
            break
    words = ''.join(f'<text x="42" y="{100+i*42}" fill="#edf2ff" font-size="26">{escape(line)}</text>' for i, line in enumerate(wrapped[:5]))
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360"><rect width="640" height="360" rx="18" fill="#14263a"/><path d="M42 40h70" stroke="#7de0ce" stroke-width="5"/>'+words+'<text x="42" y="325" fill="#a1b2cd" font-size="17">'+escape(label)+'</text></svg>').encode()


def _pdf(path, directory):
    try:
        directory.mkdir(parents=True, exist_ok=True)
        import fcntl
        with (directory / 'lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            if (directory / 'first.jpg').is_file():
                return
            try:
                import tempfile
                with tempfile.TemporaryDirectory(prefix='slides-pdf-') as work:
                    subprocess.run(['pdftoppm','-f','1','-singlefile','-scale-to','640','-jpeg',str(path),str(Path(work)/'first')], check=True, timeout=25, capture_output=True)
                    (directory / 'first.jpg').write_bytes((Path(work)/'first.jpg').read_bytes())
            except (OSError, subprocess.SubprocessError):
                (directory / 'failed').touch()
    finally:
        with LOCK:
            PENDING.discard(str(directory))


def thumbnail(path, state):
    if path.suffix.lower() == '.html':
        raw = path.read_bytes()
        if len(raw) > 8_000_000:
            return svg(['Preview unavailable'], 'HTML'), 'image/svg+xml', 'unavailable'
        manifest = path.parent / 'navigation' / 'thumbnails.json'
        image = path.parent / 'navigation' / 'thumbnails' / 'slide-01.png'
        # All helper assets must stay in the same physical deck, with no symlinks.
        parts = [manifest, image, image.parent, image.parent.parent]
        if all(not p.is_symlink() for p in parts) and manifest.is_file() and image.is_file() and image.stat().st_size < 10_000_000:
            try:
                if json.loads(manifest.read_text()).get('source_sha256') == hashlib.sha256(raw).hexdigest() and image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
                    return image, 'image/png', 'ready'
            except (ValueError, OSError, AttributeError):
                pass
        text = extract(path)
        lines = text[0][1].splitlines()[:6] if text else []
        return svg(lines or ['No static preview available'], 'HTML · text preview' if lines else 'Canvas/custom HTML · open to view'), 'image/svg+xml', 'ready' if lines else 'unavailable'
    if path.suffix.lower() == '.pptx':
        result = pptx_preview.status(path)
        if result['status'] == 'ready':
            return pptx_preview.cache_dir(path)/'page-1.jpg', 'image/jpeg', 'ready'
        return svg(['Preparing preview' if result['status']=='processing' else 'Preview unavailable'], 'PowerPoint'), 'image/svg+xml', result['status']
    if path.suffix.lower() == '.pdf':
        digest = pptx_preview.cache_dir(path).name
        directory = state / 'thumbnails' / digest
        if (directory / 'first.jpg').is_file():
            return directory/'first.jpg', 'image/jpeg', 'ready'
        if (directory / 'failed').exists():
            return svg(['Preview unavailable'], 'PDF'), 'image/svg+xml', 'unavailable'
        with LOCK:
            if str(directory) not in PENDING:
                PENDING.add(str(directory))
                POOL.submit(_pdf, path, directory)
        return svg(['Preparing preview'], 'PDF'), 'image/svg+xml', 'processing'
    return svg(['Preview unavailable']), 'image/svg+xml', 'unavailable'
