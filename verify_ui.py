"""Optional browser regression checks: pip install playwright; playwright install chromium."""
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import threading

from playwright.sync_api import sync_playwright, expect
from werkzeug.security import generate_password_hash
from werkzeug.serving import WSGIRequestHandler, make_server


class QuietHandler(WSGIRequestHandler):
    def log(self, *args, **kwargs):
        pass  # Never emit bearer paths, even for synthetic shares.


with tempfile.TemporaryDirectory(prefix='slides-ui-') as temporary:
    fixture = Path(temporary)
    root = fixture / 'library'
    root.mkdir()
    for i, name in enumerate(['Alpha', 'Bravo', 'Charlie', 'Delta']):
        folder = root / name.lower()
        folder.mkdir()
        source = folder / 'index.html'
        source.write_text('<h1>Synthetic presentation</h1>')
        os.utime(source, (1700000000 + i * 86400,) * 2)
    originals = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.glob('*/index.html')}
    config = fixture / 'auth.json'
    config.write_text(json.dumps(dict(username='test', password_hash=generate_password_hash('synthetic-password'), session_secret=secrets.token_hex(32))))
    os.environ.update(SLIDES_ROOT=str(root), SLIDES_CONFIG=str(config), SLIDES_DB=str(fixture / 'state.sqlite'))
    spec = importlib.util.spec_from_file_location('slides_ui', Path(__file__).with_name('app.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    certificate, key = fixture / 'cert.pem', fixture / 'key.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(key), '-out', str(certificate), '-days', '1', '-subj', '/CN=localhost'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    server = make_server('127.0.0.1', 0, module.app, ssl_context=(str(certificate), str(key)), request_handler=QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(ignore_https_errors=True, viewport={'width': 1440, 'height': 1000})
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            origin = f'https://localhost:{server.server_port}'
            page.goto(origin)
            page.get_by_label('Username').fill('test')
            page.get_by_label('Password').fill('synthetic-password')
            page.get_by_role('button', name='Sign in').click()
            expect(page.get_by_role('heading', name='Slide library')).to_be_visible()

            def row(name):
                return page.locator(f'.folder-row[data-title="{name}"]')

            def toggle(name, field):
                target = row(name)
                if not target.get_attribute('open') == '':
                    target.locator('summary').click()
                button = target.locator(f'[data-preference="{field}"]')
                before = button.get_attribute('aria-pressed')
                button.click()
                expect(button).to_have_attribute('aria-pressed', 'false' if before == 'true' else 'true')

            toggle('Bravo', 'pinned')
            toggle('Delta', 'pinned')
            toggle('Bravo', 'favorite')
            expected = {
                'name-asc': ['Bravo', 'Delta', 'Alpha', 'Charlie'],
                'name-desc': ['Delta', 'Bravo', 'Charlie', 'Alpha'],
                'modified-desc': ['Delta', 'Bravo', 'Charlie', 'Alpha'],
                'modified-asc': ['Bravo', 'Delta', 'Alpha', 'Charlie'],
            }
            for mode, order in expected.items():
                page.locator(f'[data-sort="{mode}"]').click()
                assert page.locator('.folder-row').evaluate_all('(rows)=>rows.map(row=>row.dataset.title)') == order
                assert row('Bravo').get_attribute('open') == ''
            page.get_by_role('button', name='Favorites only').click()
            expect(page.locator('.folder-row:visible')).to_have_count(1)
            page.get_by_role('searchbox').fill('missing')
            expect(page.locator('#empty')).to_be_visible()
            page.get_by_role('searchbox').fill('bravo')
            expect(row('Bravo')).to_be_visible()
            page.reload()
            expect(page.get_by_role('button', name='Favorites only')).to_have_attribute('aria-pressed', 'true')
            expect(page.locator('[data-sort="modified-asc"]')).to_have_attribute('aria-pressed', 'true')
            expect(page.locator('.folder-row:visible')).to_have_count(1)
            row('Bravo').locator('summary').click()
            toggle('Bravo', 'favorite')
            expect(page.locator('#empty')).to_be_visible()
            expect(page.get_by_role('button', name='Favorites only')).to_be_focused()
            page.get_by_role('button', name='Favorites only').click()
            # Failed saves leave the previous state intact and announce a retry.
            page.route('**/preferences/*', lambda route: route.fulfill(status=500, body='failed'))
            row('Alpha').locator('summary').click()
            row('Alpha').locator('[data-preference="favorite"]').click()
            expect(page.locator('#preference-status')).to_contain_text('Could not save')
            expect(row('Alpha').locator('[data-preference="favorite"]')).to_have_attribute('aria-pressed', 'false')
            page.unroute('**/preferences/*')
            for width in [1440, 390, 320]:
                page.set_viewport_size({'width': width, 'height': 1000})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                for button in page.locator('.sort-button').all():
                    assert button.bounding_box()['height'] >= 40
            # Keyboard activation and mobile persistence use the same accessible buttons.
            page.locator('[data-sort="name-desc"]').focus()
            page.keyboard.press('Space')
            expect(page.locator('[data-sort="name-desc"]')).to_have_attribute('aria-pressed', 'true')
            toggle('Alpha', 'favorite')
            page.reload()
            row('Alpha').locator('summary').click()
            expect(row('Alpha').locator('[data-preference="favorite"]')).to_have_attribute('aria-pressed', 'true')
            page.screenshot(path='/tmp/slides-library-mobile.png', full_page=True)
            page.set_viewport_size({'width': 1440, 'height': 1000})
            page.screenshot(path='/tmp/slides-library-desktop.png', full_page=True)
            # Tags combine with favorites and survive reloads without closing folders.
            target=row('Alpha')
            target.locator('input[name="tags"]').fill('  Launch , COFFEE ')
            target.locator('.tag-editor button').click()
            expect(page.locator('[data-tag="coffee"]')).to_be_visible()
            expect(target).to_have_attribute('data-tags','["coffee","launch"]')
            page.locator('[data-tag="coffee"]').click()
            expect(page.locator('.folder-row:visible')).to_have_count(1)
            page.get_by_role('button',name='Favorites only').click()
            expect(target).to_be_visible()
            page.reload()
            expect(page.locator('[data-tag="coffee"]')).to_have_attribute('aria-pressed','true')
            expect(page.locator('.folder-row:visible')).to_have_count(1)
            page.get_by_role('button',name='Favorites only').click()
            page.locator('[data-tag="coffee"]').click()
            # Mobile upload and immutable history controls.
            page.goto(origin+'/upload')
            page.locator('#deck-name').fill('browser-upload')
            page.locator('#deck-files').set_input_files({'name':'index.html','mimeType':'text/html','buffer':b'<h1>Browser upload synthetic topic</h1>'})
            page.locator('#publish').click()
            expect(page.get_by_role('heading',name='Browser Upload',exact=True)).to_be_visible()
            expect(page.get_by_role('heading',name='Revision',exact=False)).to_be_visible()
            assert not (root/'browser-upload').exists()
            page.goto(origin+'/search?q=browser')
            expect(page.locator('.search-result')).to_have_count(1)
            # Supported canvas adapter: two windows, private notes, next preview and reconnect.
            canvas=root/'canvas';canvas.mkdir()
            (canvas/'index.html').write_text('<h1 id="position">First</h1><script>const slides = [];slides.push({h:"First"},{h:"Second"});let idx=0;function go(i){idx=Math.max(0,Math.min(1,i));document.querySelector("#position").textContent=slides[idx].h;location.hash=String(idx+1)}function fit(){}</script>')
            page.goto(origin+'/view/canvas/index.html')
            with page.expect_popup() as opened:
                page.locator('#presenter-link').click()
            presenter=opened.value
            expect(presenter.locator('#connection')).to_contain_text('Audience connected')
            presenter.locator('#private-notes').fill('Private first line\nPrivate second line')
            presenter.locator('#notes-form button').click()
            expect(presenter.locator('#notes-status')).to_have_text('Notes saved.')
            presenter.locator('#next').click()
            expect(presenter.locator('#position')).to_have_text('2 / 2')
            expect(page.frame_locator('iframe').locator('#position')).to_have_text('Second')
            expect(presenter.locator('#active-note')).to_have_text('Private second line')
            assert 'Private second line' not in page.content()
            presenter.locator('#previous').click()
            expect(presenter.frame_locator('#next-preview').locator('#position')).to_have_text('Second')
            page.reload()
            expect(presenter.locator('#position')).to_have_text('1 / 2')
            expect(presenter.locator('#connection')).to_contain_text('Audience connected')
            presenter.locator('#next').click()
            expect(page.frame_locator('iframe').locator('#position')).to_have_text('Second')
            presenter.reload()
            expect(presenter.locator('#private-notes')).to_have_value('Private first line\nPrivate second line')
            expect(presenter.locator('#connection')).to_contain_text('Audience connected')
            presenter.evaluate('window.open=()=>null')
            presenter.locator('#open-audience').click()
            expect(presenter.locator('#connection')).to_contain_text('Popup blocked')
            presenter.close()
            assert not errors, errors
            context.close()
            browser.close()
        assert all((p.read_bytes(), p.stat().st_mtime_ns) == original for p, original in originals.items())
        print('Browser checks passed: all sort modes, pinned groups, search, expansion, favorites, persistence, errors, keyboard, desktop/mobile and unchanged originals')
    finally:
        server.shutdown()
        thread.join(timeout=5)
