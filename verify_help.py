"""Public authoring-help acceptance with synthetic credentials/content only."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect
from werkzeug.serving import WSGIRequestHandler,make_server

class Quiet(WSGIRequestHandler):
    def log(self,*args,**kwargs):pass

with tempfile.TemporaryDirectory(prefix='slides-help-') as temporary:
    fixture=Path(temporary);library=fixture/'library';library.mkdir()
    config=fixture/'auth.json';config.write_text(json.dumps({'session_secret':'synthetic-session-secret','username':'synthetic','password_hash':'unused','share_copy_secret':'synthetic-copy-secret'}))
    os.environ.update(SLIDES_ROOT=str(library),SLIDES_CONFIG=str(config),SLIDES_DB=str(fixture/'state.sqlite'))
    spec=importlib.util.spec_from_file_location('help_fixture',Path(__file__).with_name('app.py'));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    guest=mod.app.test_client();origin='https://localhost:8447'
    source=Path(__file__).with_name('SLIDE_AUTHORING.md').read_text()
    # Help must not even inspect authentication or private application data.
    with patch.object(mod,'logged_in',side_effect=AssertionError('Help read authentication')),patch.object(mod,'catalog',side_effect=AssertionError('Help read catalog')),patch.object(mod,'db',side_effect=AssertionError('Help opened state')):
        for path in ('/help','/help/authoring.md','/help/starter.html'):
            response=guest.get(path,base_url=origin)
            assert response.status_code==200,(path,response.status_code)
            assert 'Set-Cookie' not in response.headers
            assert b'data-bootstrap' not in response.data and b'synthetic-session-secret' not in response.data
            assert guest.head(path,base_url=origin).status_code==200
        response=guest.get('/help',base_url=origin);assert b'window.slidesDeck' in response.data and b'&lt;script&gt;' in response.data
        assert b'<script>' not in response.data and b'/static/ui/' not in response.data
        assert 'text/markdown' in response.headers['Link'] and 'Accept' in response.vary
        assert guest.get('/help/authoring.md',base_url=origin).data.decode()==source
        response=guest.get('/help',base_url=origin,headers={'Accept':'text/markdown'})
        assert response.data.decode()==source and response.mimetype=='text/markdown' and 'Accept' in response.vary
        response=guest.get('/help/starter.html',base_url=origin)
        assert 'attachment' in response.headers['Content-Disposition'] and b'window.slidesDeck' in response.data
    assert not (fixture/'state.sqlite').exists(),'Public documentation created private state'
    for path in ('/','/upload','/shares','/search','/presenter/demo/index.html','/help/../../secrets/auth.json'):
        assert guest.get(path,base_url=origin).status_code in (302,404)
    # Examples and prose stay inert even if a future guide includes HTML-like text.
    with patch.object(mod,'authoring_source',return_value='# Guide\n\n## Example\n\n<img src=x onerror=alert(1)>\n\n```html\n</code><script>window.exampleExecuted=true</script>\n```'):
        escaped=guest.get('/help',base_url=origin).data
        assert b'&lt;img' in escaped and b'&lt;script&gt;' in escaped and b'<script>' not in escaped
    cert,key=fixture/'cert.pem',fixture/'key.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    server=make_server('127.0.0.1',0,mod.app,ssl_context=(str(cert),str(key)),request_handler=Quiet);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(args=['--ignore-certificate-errors']);context=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1000});page=context.new_page();errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            site=f'https://localhost:{server.server_port}';page.goto(site+'/help')
            expect(page.get_by_role('heading',name='Slide authoring help',exact=True)).to_be_visible()
            assert page.evaluate('typeof window.slidesDeck')=='undefined','An example executed in help'
            assert not context.cookies(),'Help created a session cookie'
            for width in (1440,390,320):
                page.set_viewport_size({'width':width,'height':1000})
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                for button in page.locator('.help-actions a').all():assert button.bounding_box()['height']>=44
            page.locator('.help-contents').get_by_role('link',name='Animated decks',exact=True).click()
            assert page.url.endswith('#animated-decks')
            with page.expect_download() as pending:page.get_by_role('link',name='Download starter HTML',exact=True).click()
            downloaded=fixture/'starter.html';pending.value.save_as(downloaded)
            assert downloaded.read_bytes()==Path(__file__).with_name('static').joinpath('help/starter.html').read_bytes()
            # Load the downloaded starter through the same serving path as a real upload.
            deck=library/'starter';deck.mkdir();(deck/'index.html').write_bytes(downloaded.read_bytes())
            with mod.app.test_request_context('/'):rendered=mod.presentation_file(deck/'index.html').get_data()
            page.route('**/starter-preview',lambda route:route.fulfill(content_type='text/html',body=rendered))
            page.goto(site+'/starter-preview');player=page.locator('slides-player')
            expect(player.locator('.counter')).to_have_text('Slide 1 / 2')
            player.get_by_role('button',name='Next',exact=True).click();expect(player.locator('.counter')).to_have_text('Slide 1 / 2');expect(player.locator('.step')).to_have_text('Step 2 / 2')
            player.get_by_role('button',name='Next',exact=True).click();expect(player.locator('.counter')).to_have_text('Slide 2 / 2')
            player.get_by_role('button',name='Open slide thumbnails').click();player.get_by_role('button',name='First slide',exact=True).click();expect(player.locator('.counter')).to_have_text('Slide 1 / 2')
            assert not errors,errors
            context.close();browser.close()
        print('Public help passed: anonymous HTML/Markdown/starter, no private state or bootstrap, inert examples, narrow access, desktop/mobile layout, download and working shared-player starter')
    finally:server.shutdown();thread.join(timeout=5)
