#!/usr/bin/env python3
"""Generate local slide thumbnails for canvas decks exposing slides/go APIs."""
import argparse
import getpass
import hashlib
import json
from pathlib import Path
from urllib.parse import quote, urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True, help='HTTPS origin of the slide library')
    parser.add_argument('--deck', required=True, help='Library folder name')
    parser.add_argument('--source', type=Path, required=True, help='Matching local original HTML file')
    parser.add_argument('--output', type=Path, required=True, help='Local thumbnail output directory')
    parser.add_argument('--username', default='admin')
    args = parser.parse_args()
    parsed = urlsplit(args.base_url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        parser.error('--base-url must be an HTTPS origin without credentials, a path or query')
    if args.deck in ('.', '..') or any(c in args.deck for c in '/\\'):
        parser.error('--deck must be one library folder name')
    source = args.source.resolve(strict=True)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    output = args.output.resolve()
    if output == source.parent or source.parent in output.parents:
        parser.error('--output must be outside the original presentation folder')
    output.mkdir(parents=True, mode=0o700, exist_ok=True)
    password = getpass.getpass('Library password: ')
    from playwright.sync_api import sync_playwright
    base = args.base_url.rstrip('/')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={'width': 640, 'height': 480})
        page.goto(base + '/login')
        page.locator('#username').fill(args.username)
        page.locator('#password').fill(password)
        page.get_by_role('button', name='Sign in').click()
        page.wait_for_url(base + '/')
        page.goto(base + '/decks/' + quote(args.deck, safe='') + '/index.html?embedded=1')
        page.evaluate('document.fonts.ready')
        titles = page.evaluate('slides.map(s=>s.h)')
        for i in range(len(titles)):
            page.evaluate('(i)=>{go(i,true);paused=true;t=slides[i].rest??8}', i)
            page.wait_for_timeout(650)
            page.locator('#stage').screenshot(path=str(output / f'slide-{i+1:02}.png'))
        browser.close()
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise SystemExit('Local source changed during generation; regenerate previews.')
    (output / 'thumbnails.json').write_text(json.dumps({'source_sha256': before, 'titles': titles}, indent=2))
    print('Generated', len(titles), 'local thumbnails. Confirm the local source matches the deployed deck before publishing.')


if __name__ == '__main__':
    main()
