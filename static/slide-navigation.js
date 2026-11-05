/* Server-owned navigation: survives replacing a presentation's HTML. */
(()=>{'use strict';
if(typeof slides==='undefined'||!Array.isArray(slides)||!slides.length||typeof go!=='function'||!document.getElementById('cv')||!document.getElementById('stage')||document.getElementById('slide-drawer'))return;
const config=document.currentScript,hasThumbs=config.dataset.thumbnails==='yes',version=config.dataset.version;
const css=document.createElement('style');css.textContent=`
#slide-drawer{position:fixed;left:0;top:0;bottom:0;width:248px;background:#101b2b;border-right:1px solid #34435b;z-index:60;overflow-y:auto;color:#eef3fa;font:14px/1.4 system-ui,sans-serif;transform:translateX(-100%)}
#slide-drawer.open{transform:none}#slide-drawer .drawer-heading{position:sticky;top:0;background:#101b2b;padding:15px 14px;border-bottom:1px solid #34435b;display:flex;align-items:center;justify-content:space-between;z-index:2;font-weight:700}
#slide-drawer button,#slide-nav-bar button{font:600 13px system-ui,sans-serif;cursor:pointer;color:#eef3fa;background:#1a2a41;border:1px solid #425570;border-radius:7px;padding:7px 10px}
#slide-drawer button:focus-visible,#slide-nav-bar button:focus-visible{outline:3px solid #65dbcf;outline-offset:2px}
#slide-drawer .slide-thumb{display:block;width:calc(100% - 24px);padding:7px;margin:12px;text-align:left;background:#17243a;border:2px solid transparent;border-radius:9px}
#slide-drawer .slide-thumb[aria-current=true]{border-color:#65dbcf;background:#203c4b}
#slide-drawer .thumb-picture{aspect-ratio:16/9;background:#0c1420;border-radius:4px;overflow:hidden;display:grid;place-items:center;margin-bottom:7px}
#slide-drawer .thumb-picture img{width:100%;height:100%;object-fit:contain;display:block}
#slide-drawer .thumb-fallback{font-size:28px;color:#8da4c3}#slide-drawer .thumb-label{display:block;font-size:12px;line-height:1.4;font-weight:500}
#slide-nav-bar{position:fixed;top:0;left:0;right:0;min-height:48px;display:flex;align-items:center;gap:14px;padding:8px 14px;background:#101b2b;border-bottom:1px solid #34435b;z-index:50;font:13px system-ui,sans-serif;color:#c0cde0}
#slide-nav-bar .nav-current{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0}#slide-drawer-backdrop{display:none;position:fixed;inset:0;background:#0009;border:0;z-index:55}
@media(max-width:899px){#slide-drawer{width:min(280px,86vw)}#slide-drawer-backdrop.open{display:block}}
/* Keep playback hidden until its bottom-right hit area is hovered. */
@media(hover:hover) and (pointer:fine){
 .ui{opacity:0!important;transition:opacity .18s ease!important;padding:18px 8px 8px;right:16px!important;bottom:0!important}
 .ui:hover,.ui:has(:focus-visible){opacity:1!important}
}
@media(max-width:899px){
 .ui{display:grid!important;grid-template-columns:repeat(4,minmax(0,1fr));left:8px!important;right:8px!important;bottom:8px!important;width:auto!important;gap:6px!important;padding:6px!important;border:1px solid #34435b;border-radius:10px;background:#101b2bf2}
 .ui button{min-width:0;min-height:44px;padding:7px 5px!important;font-size:12px!important;line-height:1.25;white-space:normal}
 .ui button:nth-child(n+5){grid-column:span 2}
 .ui button:last-child:nth-child(odd){grid-column:1/-1}
}
@media(max-width:899px) and (orientation:landscape){
 .ui{grid-template-columns:repeat(auto-fit,minmax(68px,1fr))}
 .ui button:nth-child(n+5),.ui button:last-child:nth-child(odd){grid-column:auto}
}
@media(prefers-reduced-motion:reduce){.ui{transition:none!important}}
@media print{#slide-drawer,#slide-nav-bar,#slide-drawer-backdrop{display:none!important}}
`;document.head.appendChild(css);
let opened=innerWidth>=900;
const drawer=document.createElement('aside');drawer.id='slide-drawer';drawer.setAttribute('aria-label','Slide thumbnails');
const heading=document.createElement('div');heading.className='drawer-heading';heading.append(document.createTextNode('Slides'));
const close=document.createElement('button');close.type='button';close.textContent='×';close.setAttribute('aria-label','Close slide drawer');heading.append(close);drawer.append(heading);
const bar=document.createElement('nav');bar.id='slide-nav-bar';bar.setAttribute('aria-label','Slide navigation');
const toggle=document.createElement('button');toggle.type='button';toggle.textContent='☰ Slides';toggle.setAttribute('aria-controls','slide-drawer');
const current=document.createElement('span');current.className='nav-current';bar.append(toggle,current);
const backdrop=document.createElement('button');backdrop.id='slide-drawer-backdrop';backdrop.type='button';backdrop.setAttribute('aria-label','Close slide drawer');
document.body.append(drawer,backdrop,bar);
const buttons=slides.map((slide,i)=>{const button=document.createElement('button');button.type='button';button.className='slide-thumb';button.dataset.slide=String(i);button.setAttribute('aria-label',`Slide ${i+1}: ${slide.h}`);const picture=document.createElement('span');picture.className='thumb-picture';const fallback=document.createElement('span');fallback.className='thumb-fallback';fallback.textContent=String(i+1).padStart(2,'0');picture.append(fallback);if(hasThumbs){const img=document.createElement('img');img.alt='';img.loading='lazy';img.src=new URL(`navigation/thumbnails/slide-${String(i+1).padStart(2,'0')}.png?v=${version}`,location.href).href;img.onload=()=>fallback.remove();img.onerror=()=>img.remove();picture.append(img)}const label=document.createElement('span');label.className='thumb-label';label.textContent=`${i+1}. ${slide.h}`;button.append(picture,label);button.onclick=()=>{go(i);if(innerWidth<900)setOpen(false);const stage=document.getElementById('stage');stage.tabIndex=-1;stage.focus({preventScroll:true})};drawer.append(button);return button});
function sync(){buttons.forEach((button,i)=>button.setAttribute('aria-current',String(i===idx)));current.textContent=`${idx+1} / ${slides.length} · ${slides[idx].h}`;if(opened)buttons[idx]?.scrollIntoView({block:'nearest'})}
function setOpen(value){opened=value;drawer.classList.toggle('open',opened);drawer.inert=!opened;drawer.setAttribute('aria-hidden',String(!opened));toggle.setAttribute('aria-expanded',String(opened));backdrop.classList.toggle('open',opened&&innerWidth<900);fit();}
const originalGo=go;go=function(i,keepHash){originalGo(i,keepHash);sync()};
fit=function(){const left=opened&&innerWidth>=900?248:0;bar.style.left=left+'px';const top=bar.getBoundingClientRect().height;const viewport=document.getElementById('viewport');viewport.style.left=left+'px';viewport.style.top=top+'px';const bottom=innerWidth<900&&matchMedia('(hover:none)').matches?(document.querySelector('.ui')?.getBoundingClientRect().height||0)+16:0;viewport.style.bottom=bottom+'px';const scale=Math.min((innerWidth-left)/1600,Math.max(1,innerHeight-top-bottom)/900)*(document.fullscreenElement?1:.96);document.getElementById('stage').style.transform=`translate(-50%,-50%) scale(${scale})`;const dpr=Math.min(devicePixelRatio||1,2)*Math.max(scale,.5);cv.width=Math.round(CW*dpr);cv.height=Math.round(CH*dpr);ctx.setTransform(cv.width/CW,0,0,cv.height/CH,0,0)};
toggle.onclick=()=>setOpen(!opened);close.onclick=()=>{setOpen(false);toggle.focus()};backdrop.onclick=()=>setOpen(false);
addEventListener('resize',()=>setOpen(opened));document.addEventListener('fullscreenchange',()=>fit());addEventListener('keydown',e=>{if(e.key==='Escape'&&opened){setOpen(false);toggle.focus()}});
document.getElementById('stage').addEventListener('click',e=>{if(e.target.closest('a,button,input,select,textarea'))return;e.stopImmediatePropagation();const rect=e.currentTarget.getBoundingClientRect();go(idx+(e.clientX>rect.left+rect.width/2?1:-1))},true);
setOpen(opened);sync();
})();
