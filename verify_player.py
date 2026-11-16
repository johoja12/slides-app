"""Shared player acceptance: synthetic content only, authenticated and anonymous scopes."""
import base64
import json
from pathlib import Path
import re
import runpy
import subprocess
import tempfile
import threading
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect
from werkzeug.serving import WSGIRequestHandler,make_server
from verify_motion import make_pptx

fixture=runpy.run_path(str(Path(__file__).with_name('verify.py')))
mod,root,client,csrf,origin=(fixture[key] for key in ('mod','root','c','csrf','origin'))
htmls={
 'canonical':'''<main data-slides-stage><h1 id="native-position">Synthetic content</h1></main><script>let index=0,step=0;const titles=['One','Two','Three'];window.slidesDeck={version:1,titles,getState:()=>({index,count:3,step,steps:2}),go:n=>{index=n;step=0;history.replaceState(null,'','#'+(n+1));},next:()=>{if(step===0)step=1;else{index=Math.min(2,index+1);step=0}},previous:()=>{if(step)step=0;else index=Math.max(0,index-1)}};</script>''',
 'policy':'''<main id="slide"><h1>Synthetic builds</h1></main><div class="presenter-controls"><button id="play">Play</button><button id="replay">Replay</button></div><button id="slide-picker-toggle">Old picker</button><script>let slide=0,build=0;window.policyDeck={titles:['One','Two','Three'],getState:()=>({slide,build,builds:1,total:3,playing:false}),go:n=>{slide=n;build=0;},next:()=>{if(build===0)build=1;else{slide=Math.min(2,slide+1);build=0}},prev:()=>{if(build)build=0;else slide=Math.max(0,slide-1)}};document.addEventListener('keydown',e=>{if(e.key==='ArrowRight')policyDeck.next()});</script>''',
 'canvas':'''<h1 id="native-position">One</h1><div class="ui"><button id="pause">Pause</button><button id="replay">Replay</button></div><script>const slides = [];slides.push({h:'One'},{h:'Two'},{h:'Three'});let idx=0;function go(n){idx=Math.min(2,Math.max(0,n));document.querySelector('#native-position').textContent=slides[idx].h;location.hash=String(idx+1)}function fit(){}document.addEventListener('keydown',e=>{if(e.key==='ArrowRight')go(idx+1)});</script>''',
 'sections':'<section data-slide data-title="One"><h1>One</h1></section><section data-slide data-title="Two"><h1>Two</h1></section><section data-slide data-title="Three"><h1>Three</h1></section>',
}
for name,html in htmls.items():
 folder=root/('player-'+name);folder.mkdir();(folder/'index.html').write_text(html)
folder=root/'player-pptx';folder.mkdir();pptx=make_pptx(folder/'demo.pptx');cache=mod.pptx_preview.cache_dir(pptx);cache.mkdir(parents=True)
originals={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in root.glob('player-*/*') if p.is_file()}
class Quiet(WSGIRequestHandler):
 def log(self,*args,**kwargs):pass
with tempfile.TemporaryDirectory(prefix='slides-player-') as temporary:
 cert,key=Path(temporary)/'cert.pem',Path(temporary)/'key.pem'
 subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 server=make_server('127.0.0.1',0,mod.app,ssl_context=(str(cert),str(key)),request_handler=Quiet);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch();context=browser.new_context(ignore_https_errors=True,viewport={'width':390,'height':844},has_touch=True,reduced_motion='reduce')
   site=f'https://localhost:{server.server_port}'
   context.add_cookies([{'name':'__Host-slides','value':client.get_cookie('__Host-slides',domain='localhost').value,'url':site,'secure':True,'httpOnly':True,'sameSite':'Lax'}])
   page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   jpeg=base64.b64decode(page.evaluate('()=>{const c=document.createElement("canvas");c.width=160;c.height=90;c.getContext("2d").fillRect(0,0,160,90);return c.toDataURL("image/jpeg").split(",")[1]}'))
   for i in range(1,4):(cache/f'page-{i}.jpg').write_bytes(jpeg)
   (cache/'manifest.json').write_text('{"status":"ready","pages":3}')
   shared_labels=None
   for name in (*htmls,'pptx'):
    path=f'/view/player-{name}/'+('demo.pptx' if name=='pptx' else 'index.html')
    page.goto(site+path);frame=page.frame_locator('iframe');player=frame.locator('slides-player')
    expect(player.locator('.counter')).to_have_text('Slide 1 / 3')
    labels=player.locator('footer button').evaluate_all('(buttons)=>buttons.map(b=>b.id)')
    if shared_labels is None:shared_labels=labels
    assert labels==shared_labels
    player.get_by_role('button',name='Next',exact=True).click()
    expect(player.locator('.counter')).to_have_text('Slide 1 / 3' if name in ('canonical','policy') else 'Slide 2 / 3')
    if name in ('canonical','policy'):
     expect(player.locator('.step')).to_have_text('Step 2 / 2')
     player.get_by_role('button',name='Next',exact=True).click();expect(player.locator('.counter')).to_have_text('Slide 2 / 3')
    for width,height in ((320,720),(390,844),(844,390),(1440,1000)):
     page.set_viewport_size({'width':width,'height':height})
     assert player.locator('footer').evaluate('(el)=>el.scrollWidth<=el.clientWidth')
     toggle=player.get_by_role('button',name='Open slide thumbnails');toggle.click()
     dialog=player.get_by_role('dialog',name='Jump to slide');expect(dialog.locator('.card')).to_have_count(3)
     before=player.locator('.counter').text_content();page.keyboard.press('ArrowRight');expect(player.locator('.counter')).to_have_text(before)
     dialog.get_by_role('button',name='Last slide',exact=False).click();expect(player.locator('.counter')).to_have_text('Slide 3 / 3')
     toggle.click();dialog.locator('.card').first.click();expect(player.locator('.counter')).to_have_text('Slide 1 / 3')
     toggle.click();page.keyboard.press('Escape');expect(toggle).to_be_focused()
    if name in ('canvas','policy'):
     expect(frame.locator('.ui' if name=='canvas' else '.presenter-controls')).not_to_be_visible()
    if name in ('canonical','policy'):
     content=page.frames[1];content.evaluate('slidesPlayerController.go(0)')
     content.evaluate('''() => {
       const target=document.querySelector('[data-slides-stage],#slide');
       const start=new Touch({identifier:1,target,clientX:280,clientY:200});
       target.dispatchEvent(new TouchEvent('touchstart',{touches:[start],changedTouches:[start],bubbles:true,cancelable:true}));
       const end=new Touch({identifier:1,target,clientX:100,clientY:200});
       target.dispatchEvent(new TouchEvent('touchend',{touches:[],changedTouches:[end],bubbles:true,cancelable:true}));
     }''')
     expect(player.locator('.step')).to_have_text('Step 2 / 2')
     content.evaluate('slidesPlayerController.go(0)')
    # One captured arrow press advances exactly one step/slide despite legacy handlers.
    frame.locator('body').press('ArrowRight');expect(player.locator('.counter')).to_have_text('Slide 1 / 3' if name in ('canonical','policy') else 'Slide 2 / 3')
   # Same public chrome and scoped sources on an anonymous share; no private bootstrap.
   response=client.post('/shares',base_url=origin,data={'csrf':csrf,'deck':'player-sections','days':'7'})
   share=urlsplit(re.search(rb'id="share-link" readonly value="([^"]+)"',response.data).group(1).decode()).path
   anonymous=browser.new_context(ignore_https_errors=True,viewport={'width':390,'height':844})
   public=anonymous.new_page();public.goto(site+share+'index.html?embedded=1');shared=public.locator('slides-player')
   expect(shared.locator('.counter')).to_have_text('Slide 1 / 3');shared.get_by_role('button',name='Open slide thumbnails').click();shared.get_by_role('button',name='Last slide',exact=False).click();expect(shared.locator('.counter')).to_have_text('Slide 3 / 3')
   assert '__SLIDES_BOOTSTRAP__' not in public.content()
   with mod.db() as conn:conn.execute('UPDATE shares SET revoked=1 WHERE token=?',(mod.token_hash(share.split('/')[2]),))
   assert anonymous.request.get(site+share+'index.html?embedded=1').status==404
   assert not errors,errors
   anonymous.close();context.close();browser.close()
  assert all((p.read_bytes(),p.stat().st_mtime_ns)==old for p,old in originals.items())
  print('Shared player passed: identical controls for canonical, legacy canvas/builds, semantic HTML and PPTX; single-step keyboard behavior, mobile/landscape/desktop thumbnails, last-slide jumps, public scopes/revocation and unchanged originals')
 finally:server.shutdown();thread.join(timeout=5)
