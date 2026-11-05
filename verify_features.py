"""Feature acceptance/security checks using only temporary synthetic fixture data."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import runpy
import stat
import time
import zipfile

fixture = runpy.run_path(str(Path(__file__).with_name('verify.py')))
mod, root, c, csrf, origin, guest = (fixture[key] for key in ('mod','root','c','csrf','origin','guest'))
checks = 0


def check(value):
    global checks
    assert value
    checks += 1


def post(path, **data):
    return c.post(path, base_url=origin, data={'csrf':csrf, **data})


def create_share(name, version='latest', revision=''):
    response = post('/shares', deck=name, days='1', version=version, revision=revision)
    check(response.status_code == 200)
    link = re.search(rb'id="share-link" readonly value="([^"]+)"',response.data).group(1).decode()
    return __import__('urllib.parse',fromlist=['urlsplit']).urlsplit(link).path


def bundle(files):
    output = BytesIO()
    with zipfile.ZipFile(output,'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    output.seek(0)
    return output


def upload(name, files, **kwargs):
    return c.post('/upload',base_url=origin,data={'csrf':csrf,'name':name,'mode':'new',**kwargs,'files':files}, content_type='multipart/form-data')


originals = {p: (p.read_bytes(),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file() and not p.is_symlink() and not any(part.startswith('.') for part in p.relative_to(root).parts)}
# Tag normalization, global rename/merge/delete, authentication and privacy.
check(guest.post('/tags/demo',base_url=origin).status_code==302)
check(c.post('/tags/demo',base_url=origin,data={'tags':'private'}).status_code==400)
check(post('/tags/demo',tags='  CUSTOMER  X , Sales, sales ').json=={'tags':['customer x','sales']})
check(post('/tags/demo',tags='a'*49).status_code==422)
check(post('/tags/demo',tags=','.join(str(i) for i in range(21))).status_code==422)
check(post('/tags/missing',tags='private').status_code==404)
check(post('/tags',action='rename',tag=' SALES ',replacement=' Revenue ').status_code==302)
with mod.db() as conn:
    check(conn.execute('SELECT tag FROM deck_tags WHERE deck=? ORDER BY tag',('demo',)).fetchall()==[('customer x',),('revenue',)])
check(post('/tags',action='rename',tag='revenue',replacement='customer x').status_code==302)
check(post('/tags',action='delete',tag='customer x').status_code==302)
# Static HTML thumbnails never execute scripts and omit private/hidden text.
(root/'content').mkdir()
(root/'content/index.html').write_text('<h1>Galactic coffee launch</h1><p>Arabica strategy</p><script>fetch("http://invalid/");const secret="scriptsecret"</script><aside class="speaker-notes">notesSecret</aside><p hidden>hiddenSecret</p>')
check(guest.get('/thumbnail/content/index.html',base_url=origin).status_code==302)
r=c.get('/thumbnail/content/index.html',base_url=origin)
check(r.status_code==200 and r.mimetype=='image/svg+xml' and b'Galactic' in r.data and b'notesSecret' not in r.data and b'scriptsecret' not in r.data)
first_thumb=r.data
(root/'content/index.html').write_text('<h1>Orbital coffee launch</h1><p>Arabica strategy</p><aside class="speaker-notes">notesSecret</aside>')
check(c.get('/thumbnail/content/index.html',base_url=origin).data!=first_thumb)
for filename in ('.env','../demo/index.html','escape','loop/index.html'):
    check(c.get('/thumbnail/demo/'+filename,base_url=origin).status_code==404)
scoped=create_share('content')
check(guest.get(scoped+'_thumbnail/index.html',base_url=origin).status_code==200)
check(guest.get(scoped+'_thumbnail/../demo/index.html',base_url=origin).status_code==404)
check(b'data-tags' not in guest.get(scoped,base_url=origin,follow_redirects=True).data)
# Snapshot migration, immutable originals, paired revisions, fixed/latest semantics.
check(post('/history/content',action='snapshot').status_code==302)
with mod.db() as conn:
    old=conn.execute('SELECT r.id FROM revisions r JOIN decks d ON d.id=r.deck_id WHERE d.name=?',('content',)).fetchone()[0]
fixed=create_share('content','fixed')
latest=create_share('content')
check(c.get(f'/r/{old}/decks/content/index.html?embedded=1',base_url=origin).status_code==200)
check(c.get(f'/r/{old}/decks/demo/index.html?embedded=1',base_url=origin).status_code==404)
check(guest.get(f'/r/{old}/decks/content/index.html',base_url=origin).status_code==302)
check(post('/history/content',action='select',revision=str(old),expected='wrong').status_code==409)
# Safe upload with an explicit replacement; old bytes and old links stay available.
r=upload('content',[(BytesIO(b'<h1>New release vocabulary</h1>'),'index.html')],mode='revision',expected='live')
check(r.status_code==200)
new=r.json['revision']
check(new!=old)
check(b'Orbital' in guest.get(fixed+'index.html',base_url=origin).data)
check(b'New release' in guest.get(latest+'index.html',base_url=origin).data)
check(b'Orbital' in (root/'content/index.html').read_bytes())
check(post('/history/content',action='select',revision=str(old),expected=str(new)).status_code==302)
check(b'Orbital' in guest.get(latest+'index.html',base_url=origin).data)
check(b'New release' in c.get(f'/r/{new}/decks/content/index.html?embedded=1',base_url=origin).data)
# Historical HTML relative assets use a revision-specific URL prefix.
r=upload('assets',[(bundle({'index.html':'<h1>Assets</h1><img src="images/a.svg">','images/a.svg':'<svg xmlns="http://www.w3.org/2000/svg"/>'}),'deck.zip')])
check(r.status_code==200)
asset_revision=r.json['revision']
check(c.get(f'/r/{asset_revision}/decks/assets/images/a.svg',base_url=origin).status_code==200)
check(c.get('/decks/assets/index.html',base_url=origin).status_code==302)
# Upload rejection, atomicity and conflict control.
check(guest.post('/upload',base_url=origin).status_code==302)
check(c.post('/upload',base_url=origin,data={'name':'no-csrf'}).status_code==400)
for bad in ['../outside','/absolute','.hidden','folder/.env','folder/../../escape']:
    check(upload('bad-bundle',[(bundle({bad:'bad','index.html':'<h1>Valid</h1>'}),'bundle.zip')]).status_code==422)
symlink=BytesIO()
with zipfile.ZipFile(symlink,'w') as archive:
    info=zipfile.ZipInfo('link');info.external_attr=(stat.S_IFLNK|0o777)<<16;archive.writestr(info,'/etc/passwd')
symlink.seek(0)
check(upload('bad-symlink',[(symlink,'link.zip')]).status_code==422)
check(upload('invalid-pdf',[(BytesIO(b'not a PDF'),'file.pdf')]).status_code==422)
check(upload('invalid-pptx',[(BytesIO(b'not zip'),'file.pptx')]).status_code==422)
check(upload('missing-asset',[(BytesIO(b'<h1>Title</h1><img src="missing.png">'),'index.html')]).status_code==422)
check(upload('assets',[(BytesIO(b'<h1>Conflict</h1>'),'index.html')]).status_code==409)
check(upload('content',[(BytesIO(b'<h1>Race</h1>'),'index.html')],mode='revision',expected='live').status_code==409)
check(not (root/'assets').exists())
with mod.db() as conn:
    check(not conn.execute('SELECT 1 FROM decks WHERE name LIKE "bad-%"').fetchone())
check(not list((mod.STATE/'ingestion').glob('upload-*')))
# Search indexes visible served slide text only, with tag/favorite scope and updates.
check(guest.get('/search?q=Orbital',base_url=origin).status_code==302)
r=c.get('/search?q=Orbital',base_url=origin)
check(r.status_code==200 and b'Orbital coffee' in r.data)
check(b'0 matching slide/page results' in c.get('/search?q=notesSecret',base_url=origin).data)
check(b'0 matching slide/page results' in c.get('/search?q=New+release',base_url=origin).data)
check(post('/tags/content',tags='launch').status_code==200)
check(b'0 matching slide/page results' in c.get('/search?q=Orbital&tag=unrelated',base_url=origin).data)
check(b'1 matching slide/page results' in c.get('/search?q=Orbital&tag=launch',base_url=origin).data)
check(b'0 matching slide/page results' in c.get('/search?q=Orbital&favorites=1',base_url=origin).data)
check(post('/preferences/content',field='favorite',value='1').status_code==200)
check(b'1 matching slide/page results' in c.get('/search?q=Orbital&favorites=1',base_url=origin).data)
for i in range(25):
    folder=root/f'search-{i}';folder.mkdir();(folder/'index.html').write_text(f'<h1>Pagination constellation {i}</h1>')
r=c.get('/search?q=constellation',base_url=origin)
check(b'25 matching slide/page results' in r.data and r.data.count(b'class="card search-result"')==20)
check(c.get('/search?q=constellation&page=2',base_url=origin).data.count(b'class="card search-result"')==5)
(root/'search-0/index.html').unlink()
check(b'24 matching slide/page results' in c.get('/search?q=constellation',base_url=origin).data)
(root/'search-1/index.html').write_text('<h1>Changed content</h1>')
check(b'23 matching slide/page results' in c.get('/search?q=constellation',base_url=origin).data)
check(c.get('/search?q=%22+OR+%3A&page=x',base_url=origin).status_code==400)
# Aggregate activity counts entry visits, not assets/reloads/bots, and respects grants.
visitor=mod.app.test_client(); ua={'User-Agent':'Synthetic human browser'}
with mod.db() as conn:
    share_id=conn.execute('SELECT id FROM shares WHERE token=?',(mod.token_hash(latest.split('/')[2]),)).fetchone()[0]
for _ in range(3):
    check(visitor.get(latest,base_url=origin,headers=ua).status_code==302)
    check(visitor.get(latest+'index.html',base_url=origin,headers=ua).status_code==200)
    check(visitor.get(latest+'_thumbnail/index.html',base_url=origin,headers=ua).status_code==200)
with mod.db() as conn:
    check(conn.execute('SELECT views,last_opened FROM share_activity WHERE share_id=?',(share_id,)).fetchone()[0]==1)
check(mod.app.test_client().get(latest,base_url=origin,headers={'User-Agent':'Search crawler bot'}).status_code==302)
with mod.db() as conn:
    check(conn.execute('SELECT views FROM share_activity WHERE share_id=?',(share_id,)).fetchone()[0]==1)
    conn.execute('UPDATE share_visits SET stamp=? WHERE share_id=?',(time.time()-1900,share_id))
check(visitor.get(latest,base_url=origin,headers=ua).status_code==302)
with mod.db() as conn:
    check(conn.execute('SELECT views FROM share_activity WHERE share_id=?',(share_id,)).fetchone()[0]==2)
check(post(f'/shares/{share_id}/activity/reset').status_code==302)
with mod.db() as conn:
    check(not conn.execute('SELECT 1 FROM share_activity WHERE share_id=?',(share_id,)).fetchone())
check(post(f'/shares/{share_id}/revoke').status_code==302)
check(visitor.get(latest,base_url=origin,headers=ua).status_code==404)
check(visitor.get(latest+'_thumbnail/index.html',base_url=origin,headers=ua).status_code==404)
# Presenter notes never enter shared responses, files, search or thumbnails.
notes_url='/presenter/content/index.html'
check(guest.get(notes_url,base_url=origin).status_code==302)
check(c.post(notes_url,base_url=origin,data={'notes':'secret'}).status_code==400)
check(post(notes_url,notes='privatePresenterSentinel\nSecond slide').json=={'saved':True})
check(b'privatePresenterSentinel' in c.get(notes_url,base_url=origin).data)
check(b'privatePresenterSentinel' not in guest.get(fixed+'index.html',base_url=origin).data)
check(b'0 matching slide/page results' in c.get('/search?q=privatePresenterSentinel',base_url=origin).data)
check(b'privatePresenterSentinel' not in c.get('/thumbnail/content/index.html',base_url=origin).data)
check(post(notes_url,notes='x'*12001).status_code==422)
check(all((p.read_bytes(),p.stat().st_mtime_ns)==original for p,original in originals.items()))
print(f'{checks} additional feature checks passed: tags, thumbnails, immutable versions, fixed/latest grants, bounded uploads, search, activity and private notes')
# Fixed revision asset scopes never borrow a missing format/asset from current files.
asset_fixed=create_share('assets','fixed')
response=upload('assets',[(BytesIO(b'<h1>Replacement without previous images</h1>'),'index.html')],mode='revision',expected=str(asset_revision))
check(response.status_code==200)
check(guest.get(asset_fixed+'images/a.svg',base_url=origin).status_code==200)
check(c.get('/decks/assets/images/a.svg',base_url=origin).status_code==404)
# Bounded decompression and conflicting concurrent publishes leave no partial deck.
import library_store
previous_limit=library_store.MAX_EXPANDED
library_store.MAX_EXPANDED=64
try:
    check(upload('oversized-bundle',[(bundle({'index.html':'x'*200}),'large.zip')]).status_code==422)
finally:
    library_store.MAX_EXPANDED=previous_limit
from concurrent.futures import ThreadPoolExecutor
cookie=c.get_cookie('__Host-slides',domain='localhost').value

def concurrent_upload(number):
    client=mod.app.test_client()
    client.set_cookie('__Host-slides',cookie,domain='localhost',secure=True)
    return client.post('/upload',base_url=origin,data={'csrf':csrf,'name':'concurrent-deck','mode':'new','files':[(BytesIO(f'<h1>Concurrent {number}</h1>'.encode()),'index.html')]},content_type='multipart/form-data').status_code

with ThreadPoolExecutor(max_workers=2) as pool:
    check(sorted(pool.map(concurrent_upload,[1,2]))==[200,409])
with mod.db() as conn:
    check(conn.execute('SELECT count(*) FROM revisions r JOIN decks d ON d.id=r.deck_id WHERE d.name=?',('concurrent-deck',)).fetchone()[0]==1)
print(f'{checks} additional feature checks passed, including fixed asset scope, decompression bounds and concurrent publication')

# Upload bodies exceed normal form limits only on the authenticated ingestion route.
check(upload('large-safe',[(BytesIO(b'<h1>Large synthetic HTML</h1>'+b' '*40000),'index.html')]).status_code==200)
check(post(notes_url,notes='ا'*12000).status_code==200)
print(f'{checks} additional feature checks passed, including upload/form limits and Unicode notes')

# Private Vue bootstrap/API boundaries and inert user-controlled metadata.
api_headers={'Accept':'application/json'}
for endpoint in ('/','/upload','/shares','/history/content','/search?q=Orbital','/presenter/content/index.html','/view/content/index.html'):
    check(guest.get(endpoint,base_url=origin,headers=api_headers).status_code==302)
    response=c.get(endpoint,base_url=origin,headers=api_headers)
    check(response.status_code==200 and response.is_json)
check(c.post('/tags/content',base_url=origin,headers=api_headers,data={'tags':'no-csrf'}).status_code==400)
response=c.post('/tags/content',base_url=origin,headers=api_headers,data={'tags':'no-csrf'})
check(response.is_json and 'error' in response.json)
response=guest.get(fixed,base_url=origin,headers=api_headers,follow_redirects=True)
check(response.status_code==200 and b'ui-bootstrap' not in response.data and b'/static/ui/' not in response.data)
response=c.get('/',base_url=origin)
bootstrap=json.loads(re.search(rb'<script id="ui-bootstrap" type="application/json">(.*?)</script>',response.data,re.S).group(1))
check(bootstrap['page']=='library' and bootstrap['csrf']==csrf and isinstance(bootstrap['data']['entries'],list))
asset=re.search(rb'<script type="module" src="([^"]+)"',response.data).group(1).decode()
check(c.get(asset,base_url=origin).status_code==200)
check(guest.get(asset,base_url=origin).status_code==302)
malicious='</script><script>globalThis.privateLeakSentinel=1</script>'
(root/'demo/metadata.json').write_text(json.dumps({'title':malicious}))
response=c.get('/',base_url=origin)
check(malicious.encode() not in response.data and b'\\u003c/script\\u003e' in response.data)
check(b'privateLeakSentinel' not in c.get(asset,base_url=origin).data)
print(f'{checks} additional feature checks passed, including Vue API authorization, CSRF, private bootstrap isolation and inert metadata encoding')
