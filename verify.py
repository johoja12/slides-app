import importlib.util,json,os,secrets,sys,tempfile,time
from pathlib import Path
from werkzeug.security import generate_password_hash
base=Path(tempfile.mkdtemp(prefix='slides-tests-'))
root=base/'library'; root.mkdir(); (root/'demo').mkdir()
(root/'demo/index.html').write_text('<h1>Deck</h1>')
(root/'demo/metadata.json').write_text('{"title":"Demo"}')
(root/'demo/.env').write_text('secret')
(root/'demo/escape').symlink_to('/etc/passwd')
(root/'demo/loop').symlink_to(root/'demo',target_is_directory=True)
conf=base/'auth.json'; conf.write_text(json.dumps({'username':'testuser','password_hash':generate_password_hash('test-password-123456'),'session_secret':secrets.token_hex(48),'share_copy_secret':secrets.token_hex(32)}))
os.environ.update(SLIDES_ROOT=str(root),SLIDES_CONFIG=str(conf),SLIDES_DB=str(base/'db'))
spec=importlib.util.spec_from_file_location('slides',str(Path(__file__).with_name('app.py'))); mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
c=mod.app.test_client(); origin='https://localhost:8447'
checks=0
def check(ok):
 global checks
 assert ok
 checks+=1
for path in ['/','/decks/demo/index.html','/decks/demo/.env']:
 check(c.get(path,base_url=origin).status_code==302)
check(c.get('/login',base_url=origin).status_code==200)
with c.session_transaction(base_url=origin) as s: csrf=s['csrf']
check(c.post('/login',base_url=origin,data={'username':'testuser','password':'test-password-123456'}).status_code==400)
check(c.post('/login',base_url=origin,data={'csrf':csrf,'username':'testuser','password':'bad'}).status_code==401)
r=c.post('/login',base_url=origin,data={'csrf':csrf,'username':'testuser','password':'test-password-123456','next':'//evil.com'})
check(r.status_code==302 and r.location=='/')
check('Secure' in r.headers['Set-Cookie'] and 'HttpOnly' in r.headers['Set-Cookie'] and 'SameSite=Lax' in r.headers['Set-Cookie'])
check(b'Demo' in c.get('/',base_url=origin).data)
check(c.get('/decks/demo/index.html',base_url=origin,follow_redirects=True).status_code==200)
for path in ['/decks/demo/escape','/decks/demo/loop/index.html','/decks/demo/.env','/decks/demo/../../etc/passwd','/secrets/auth.json']:
 check(c.get(path,base_url=origin).status_code==404)
for path in ['//evil.com','/\\evil.com','https://evil.com','/%0a']:
 if path=='/%0a': continue
 check(mod.safe_next(path)=='/')
check(c.post('/logout',base_url=origin).status_code==400)
cookie=c.get_cookie('__Host-slides',domain='localhost').value
with c.session_transaction(base_url=origin) as s: csrf=s['csrf']
check(c.post('/logout',base_url=origin,data={'csrf':csrf}).status_code==302)
c.set_cookie('__Host-slides',cookie,domain='localhost',secure=True)
check(c.get('/',base_url=origin).status_code==302) # old cookie revoked server-side
c=mod.app.test_client(); c.get('/login',base_url=origin)
with c.session_transaction(base_url=origin) as s: csrf=s['csrf']
for _ in range(10):
 check(c.post('/login',base_url=origin,data={'csrf':csrf,'username':'testuser','password':'bad'}).status_code==401)
check(c.post('/login',base_url=origin,data={'csrf':csrf,'username':'testuser','password':'bad'}).status_code==429)
print(f'{checks} security and behavior checks passed')
# Share creation, scoping, expiry and revocation.
c=mod.app.test_client();c.get('/login',base_url=origin)
with c.session_transaction(base_url=origin) as s: csrf=s['csrf']
r=c.post('/login',base_url=origin,headers={'X-Real-IP':'test-share-admin'},data={'csrf':csrf,'username':'testuser','password':'test-password-123456'})
check(r.status_code==302)
with c.session_transaction(base_url=origin) as s: csrf=s['csrf']
check(c.post('/shares',base_url=origin,data={'deck':'demo'}).status_code==400)
check(c.post('/shares',base_url=origin,data={'csrf':csrf,'deck':'missing','days':'7'}).status_code==404)
check(c.post('/shares',base_url=origin,data={'csrf':csrf,'deck':'demo','days':'999'}).status_code==400)
r=c.post('/shares',base_url=origin,data={'csrf':csrf,'deck':'demo','days':'7'})
import re
link=re.search(rb'id="share-link" readonly value="([^"]+)"',r.data).group(1).decode()
path=__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(link).path
token=path.split('/')[2]
check(len(token)==43)
guest=mod.app.test_client()
check(guest.get(path,base_url=origin).status_code==302)
check(guest.get(path+'index.html',base_url=origin).status_code==200)
check(guest.get('/',base_url=origin).status_code==302)
check(guest.get('/shares',base_url=origin).status_code==302)
check(guest.get(path+'.env',base_url=origin).status_code==404)
check(guest.get(path+'../demo/index.html',base_url=origin).status_code==404)
check(guest.get(path+'escape',base_url=origin).status_code==404)
check(guest.get('/s/'+('a'*43)+'/index.html',base_url=origin).status_code==404)
(root/'other').mkdir();(root/'other/index.html').write_text('Other private deck')
check(guest.get(path+'../other/index.html',base_url=origin).status_code==404)
with mod.db() as conn:
 row=conn.execute('SELECT id,token FROM shares ORDER BY id DESC LIMIT 1').fetchone()
 check(row[1]!=token)
 conn.execute('UPDATE shares SET expires=? WHERE id=?',(time.time()-1,row[0]))
check(guest.get(path+'index.html',base_url=origin).status_code==404)
with mod.db() as conn:conn.execute('UPDATE shares SET expires=NULL WHERE id=?',(row[0],))
check(guest.get(path+'index.html',base_url=origin).status_code==200)
check(c.post('/shares/'+str(row[0])+'/revoke',base_url=origin,data={'csrf':csrf}).status_code==302)
check(guest.get(path+'index.html',base_url=origin).status_code==404)
print(f'{checks} total checks passed, including public share scoping, expiry and revocation')

# Bulk share actions are atomic and refuse deletion of active links.
with c.session_transaction(base_url=origin) as session_data: csrf=session_data['csrf']
now=time.time()
with mod.db() as conn:
    conn.execute('INSERT INTO shares (token,deck,created,expires) VALUES (?,?,?,?)',('bulk-active','demo',now,now+86400))
    active_id=conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.execute('INSERT INTO shares (token,deck,created,expires) VALUES (?,?,?,?)',('bulk-expired','demo',now,now-10))
    expired_id=conn.execute('SELECT last_insert_rowid()').fetchone()[0]
check(c.post('/shares/bulk',base_url=origin,data={'action':'revoke','ids':[active_id]}).status_code==400)
check(c.post('/shares/bulk',base_url=origin,data={'csrf':csrf,'action':'other','ids':[active_id]}).status_code==400)
check(c.post('/shares/bulk',base_url=origin,data={'csrf':csrf,'action':'revoke','ids':['1 OR 1=1']}).status_code==400)
check(c.post('/shares/bulk',base_url=origin,data={'csrf':csrf,'action':'delete','ids':[active_id,expired_id]}).status_code==409)
with mod.db() as conn: check(conn.execute('SELECT count(*) FROM shares WHERE id IN (?,?)',(active_id,expired_id)).fetchone()[0]==2)
check(c.post('/shares/bulk',base_url=origin,data={'csrf':csrf,'action':'revoke','ids':[active_id,9999999]}).status_code==404)
with mod.db() as conn: check(conn.execute('SELECT revoked FROM shares WHERE id=?',(active_id,)).fetchone()[0]==0)
check(c.post('/shares/bulk',base_url=origin,data={'csrf':csrf,'action':'revoke','ids':[active_id,expired_id]}).status_code==302)
with mod.db() as conn: check(conn.execute('SELECT revoked FROM shares WHERE id=?',(active_id,)).fetchone()[0]==1)
check(c.post('/shares/bulk',base_url=origin,data={'csrf':csrf,'action':'delete','ids':[active_id,expired_id]}).status_code==302)
with mod.db() as conn: check(conn.execute('SELECT count(*) FROM shares WHERE id IN (?,?)',(active_id,expired_id)).fetchone()[0]==0)
check(mod.app.test_client().post('/shares/bulk',base_url=origin,data={'action':'revoke','ids':[1]}).status_code==302)
print(f'{checks} total checks passed, including bulk-action authorization, CSRF, validation and atomicity')
# PPTX previews and cached derivatives retain the original deck's access scope.
mod.pptx_preview.CACHE=base/'preview-cache'
pptx=root/'demo/sample.pptx';pptx.write_bytes(b'unchanged-original-pptx')
cache=mod.pptx_preview.cache_dir(pptx);cache.mkdir(parents=True)
(cache/'manifest.json').write_text('{"status":"ready","pages":1}')
(cache/'page-1.jpg').write_bytes(b'jpeg-fixture');(cache/'document.pdf').write_bytes(b'%PDF-fixture')
check(c.get('/view/demo/sample.pptx',base_url=origin).status_code==200)
check(c.get('/pptx/demo/sample.pptx',base_url=origin).status_code==200)
check(c.get('/pptx-data/demo/sample.pptx/manifest',base_url=origin).json['pages']==1)
r=c.get('/decks/demo/sample.pptx',base_url=origin);check(r.data==b'unchanged-original-pptx' and 'attachment' in r.headers['Content-Disposition'])
check(guest.get('/pptx-data/demo/sample.pptx/page-1.jpg',base_url=origin).status_code==302)
r=c.post('/shares',base_url=origin,data={'csrf':csrf,'deck':'demo','days':'7'})
link=re.search(rb'id="share-link" readonly value="([^"]+)"',r.data).group(1).decode();share_path=__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(link).path
check(guest.get(share_path+'_pptx/sample.pptx',base_url=origin,follow_redirects=True).status_code==200)
check(guest.get(share_path+'_pptx-data/sample.pptx/manifest',base_url=origin).json['status']=='ready')
check(guest.get(share_path+'_pptx-data/sample.pptx/page-1.jpg',base_url=origin).data==b'jpeg-fixture')
check(guest.get(share_path+'_pptx-data/sample.pptx/page-99.jpg',base_url=origin).status_code==404)
check(guest.get(share_path+'_pptx-data/../other/sample.pptx/manifest',base_url=origin).status_code==404)
with mod.db() as conn:conn.execute('UPDATE shares SET revoked=1 WHERE token=?',(mod.token_hash(share_path.split('/')[2]),))
check(guest.get(share_path+'_pptx-data/sample.pptx/page-1.jpg',base_url=origin).status_code==404)
check(guest.get(share_path+'_pptx/sample.pptx',base_url=origin).status_code==404)
pptx.write_bytes(b'new-version');check(mod.pptx_preview.cache_dir(pptx)!=cache)
print(f'{checks} total checks passed, including PPTX preview/download, cache invalidation and shared asset authorization')
# One deck can have explicitly linked HTML/PPTX formats without expanding share scope.
with mod.app.test_request_context('/'):
 entry=next(e for e in mod.catalog() if e['name']=='demo')
 check(entry['linked_formats'] and entry['format_files']['pptx']=='sample.pptx')
r=c.get('/view/demo/index.html',base_url=origin);check(b'aria-label="Presentation format"' in r.data and b'Download PPTX' in r.data)
r=c.get('/view/demo/sample.pptx',base_url=origin);check(b'aria-current="page">PowerPoint' in r.data)
r=c.post('/shares',base_url=origin,data={'csrf':csrf,'deck':'demo','days':'7'})
link=re.search(rb'id="share-link" readonly value="([^"]+)"',r.data).group(1).decode();share_path=__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(link).path
r=guest.get(share_path,base_url=origin,follow_redirects=True)
check(r.status_code==200 and b'aria-label="Presentation format"' in r.data)
check(b'Back to library' not in r.data and b'id="share-dialog"' not in r.data)
check(guest.get(share_path+'_view/sample.pptx',base_url=origin).status_code==200)
check(guest.get(share_path+'index.html?embedded=1',base_url=origin).data==b'<h1>Deck</h1>')
check(guest.get(share_path+'_view/../other/index.html',base_url=origin).status_code==404)
with mod.db() as conn:conn.execute('UPDATE shares SET revoked=1 WHERE token=?',(mod.token_hash(share_path.split('/')[2]),))
check(guest.get(share_path+'_view/sample.pptx',base_url=origin).status_code==404)
(root/'demo/other.pptx').write_bytes(b'other-content')
with mod.app.test_request_context('/'):
 check(not next(e for e in mod.catalog() if e['name']=='demo')['linked_formats'])
(root/'demo/metadata.json').write_text('{"title":"Demo","formats":{"html":"index.html","pptx":"sample.pptx"}}')
with mod.app.test_request_context('/'):
 entry=next(e for e in mod.catalog() if e['name']=='demo');check(entry['linked_formats'])
 check(not mod.linked_formats(entry,'other.pptx'))
print(f'{checks} total checks passed, including linked formats, explicit pairing, ambiguous-file handling and shared-view authorization')
# Existing share copying is repeatable, preserves legacy URLs, and obeys grants.
legacy_token=secrets.token_urlsafe(32);expiry=time.time()+3600;created=time.time()-300
with mod.db() as conn:
 legacy_id=conn.execute('INSERT INTO shares(token,deck,created,expires) VALUES (?,?,?,?)',(mod.token_hash(legacy_token),'demo',created,expiry)).lastrowid
endpoint=f'/shares/{legacy_id}/copy'
check(mod.app.test_client().post(endpoint,base_url=origin).status_code==302)
check(c.post(endpoint,base_url=origin).status_code==400)
check(c.get(endpoint,base_url=origin).status_code==405)
r=c.post(endpoint,base_url=origin,data={'csrf':csrf});check(r.status_code==200)
copy_url=r.json['url'];copy_path=__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(copy_url).path
check(c.post(endpoint,base_url=origin,data={'csrf':csrf}).json['url']==copy_url)
check(guest.get(copy_path,base_url=origin,follow_redirects=True).status_code==200)
check(guest.get('/s/'+legacy_token+'/',base_url=origin,follow_redirects=True).status_code==200)
with mod.db() as conn:
 row=conn.execute('SELECT token,copy_seed,copy_token_hash,created,expires FROM shares WHERE id=?',(legacy_id,)).fetchone()
 check(row[0]==mod.token_hash(legacy_token) and row[3]==created and row[4]==expiry)
 check(legacy_token not in row and copy_path.split('/')[2] not in row)
 conn.execute('UPDATE shares SET revoked=1 WHERE id=?',(legacy_id,))
check(c.post(endpoint,base_url=origin,data={'csrf':csrf}).status_code==410)
check(guest.get(copy_path,base_url=origin).status_code==404)
check(guest.get('/s/'+legacy_token+'/',base_url=origin).status_code==404)
with mod.db() as conn:conn.execute('UPDATE shares SET revoked=0,expires=? WHERE id=?',(time.time()-1,legacy_id))
check(c.post(endpoint,base_url=origin,data={'csrf':csrf}).status_code==410)
r=c.post('/shares',base_url=origin,data={'csrf':csrf,'deck':'demo','days':'7'})
issued=re.search(rb'id="share-link" readonly value="([^"]+)"',r.data).group(1).decode()
issued_token=__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(issued).path.split('/')[2]
with mod.db() as conn:new_id=conn.execute('SELECT id FROM shares WHERE token=?',(mod.token_hash(issued_token),)).fetchone()[0]
check(c.post(f'/shares/{new_id}/copy',base_url=origin,data={'csrf':csrf}).json['url']==issued)
check(c.post('/shares/999999999/copy',base_url=origin,data={'csrf':csrf}).status_code==404)
# Additive schema migration retains existing share records and URLs.
import sqlite3
previous_db=mod.DB;mod.DB=str(base/'old-format.sqlite')
old=sqlite3.connect(mod.DB)
old.execute('CREATE TABLE shares (id INTEGER PRIMARY KEY,token TEXT UNIQUE NOT NULL,deck TEXT NOT NULL,created REAL NOT NULL,expires REAL,revoked INTEGER NOT NULL DEFAULT 0)')
old.execute('INSERT INTO shares(token,deck,created,expires) VALUES (?,?,?,?)',('legacy-hash','demo',created,expiry));old.commit();old.close()
with mod.db() as conn:
 check({'copy_seed','copy_token_hash'}.issubset({r[1] for r in conn.execute('PRAGMA table_info(shares)')}))
 check(conn.execute('SELECT token FROM shares').fetchone()[0]=='legacy-hash')
mod.DB=previous_db
print(f'{checks} total checks passed, including repeat copying, legacy URL preservation, additive migration, CSRF, authentication, expiry and revocation')

# Share entry URLs work anonymously with or without a trailing slash.
legacy=secrets.token_urlsafe(32)
with mod.db() as conn:
 share_id=conn.execute('INSERT INTO shares(token,deck,created,expires) VALUES (?,?,?,?)',(mod.token_hash(legacy),'demo',time.time(),time.time()+3600)).lastrowid
for suffix in ['', '/']:
 response=guest.get('/s/'+legacy+suffix,base_url=origin)
 check(response.status_code==302 and '/login' not in response.location)
 check(guest.get('/s/'+legacy+suffix,base_url=origin,follow_redirects=True).status_code==200)
check(guest.get('/s/'+('z'*43),base_url=origin).status_code==404)
with mod.db() as conn:conn.execute('UPDATE shares SET revoked=1 WHERE id=?',(share_id,))
check(guest.get('/s/'+legacy,base_url=origin).status_code==404)
check(guest.get('/s/'+legacy+'/',base_url=origin).status_code==404)
print(f'{checks} total checks passed, including slashless and canonical anonymous share entry URLs')

# Public invalid links and unknown routes get useful branded errors without a login loop.
unknown=mod.app.test_client()
for path in ['/s/not-a-link','/s/'+('x'*43),'/s/'+('x'*43)+'/', '/s/', '/missing-page']:
 r=unknown.get(path,base_url=origin)
 check(r.status_code==404 and b'Go to library' in r.data and b'Try again' in r.data and b'Error 404' in r.data)
 check(b'/login?next=' not in r.data)
check(b'Link unavailable' in unknown.get('/s/not-a-link',base_url=origin).data)
print(f'{checks} total checks passed, including helpful public error pages')

# Private single-admin preferences persist independently without touching originals.
preference_url='/preferences/demo'
original=(root/'demo/index.html').read_bytes()
modified=mod.deck_modified(root/'demo')
check(guest.post(preference_url,base_url=origin,data={'field':'favorite','value':'1'}).status_code==302)
check(c.get(preference_url,base_url=origin).status_code==405)
check(c.post(preference_url,base_url=origin,data={'field':'favorite','value':'1'}).status_code==400)
for field,value in [('token','1'),('favorite','yes'),('pinned','2')]:
 check(c.post(preference_url,base_url=origin,data={'csrf':csrf,'field':field,'value':value}).status_code==400)
for name in ['missing','.hidden','demo%2Findex.html']:
 check(c.post('/preferences/'+name,base_url=origin,data={'csrf':csrf,'field':'favorite','value':'1'}).status_code==404)
for field in ['favorite','pinned','favorite']:
 response=c.post(preference_url,base_url=origin,data={'csrf':csrf,'field':field,'value':'1'})
 check(response.status_code==200 and response.json=={field:True})
with mod.db() as conn:
 check(conn.execute('SELECT favorite,pinned FROM deck_preferences WHERE deck=?',('demo',)).fetchone()==(1,1))
check(b'data-favorite="1" data-pinned="1"' in c.get('/',base_url=origin).data)
check(c.post(preference_url,base_url=origin,data={'csrf':csrf,'field':'favorite','value':'0'}).json=={'favorite':False})
with mod.db() as conn:
 check(conn.execute('SELECT favorite,pinned FROM deck_preferences WHERE deck=?',('demo',)).fetchone()==(0,1))
check((root/'demo/index.html').read_bytes()==original and mod.deck_modified(root/'demo')==modified)
# Preferences use folder identity; removed folders are hidden and renames start fresh.
(root/'demo').rename(root/'renamed-demo')
check(c.post(preference_url,base_url=origin,data={'csrf':csrf,'field':'favorite','value':'1'}).status_code==404)
check(b'data-favorite="0" data-pinned="0"' in c.get('/',base_url=origin).data)
(root/'renamed-demo').rename(root/'demo')
# Anonymous share views never include library preferences or controls.
share_token=secrets.token_urlsafe(32)
with mod.db() as conn:
 conn.execute('INSERT INTO shares(token,deck,created) VALUES (?,?,?)',(mod.token_hash(share_token),'demo',time.time()))
response=guest.get('/s/'+share_token+'/',base_url=origin,follow_redirects=True)
check(response.status_code==200 and b'data-preference' not in response.data and b'data-favorite' not in response.data)
print(f'{checks} total checks passed, including private favorites/pins, persistence, independent updates, CSRF and unchanged originals')
