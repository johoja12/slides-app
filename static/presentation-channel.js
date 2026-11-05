/* Public navigation adapter. Carries positions only; never notes or credentials. */
(()=>{'use strict';
const canvas=typeof slides!=='undefined'&&Array.isArray(slides)&&typeof go==='function'&&typeof idx!=='undefined';
const powerpoint=typeof count!=='undefined'&&typeof current!=='undefined'&&typeof go==='function';
if(!canvas&&!powerpoint)return;
function report(){parent.postMessage({type:'slides-position',index:canvas?idx:current,count:canvas?slides.length:count},location.origin)}
const previousGo=go;go=function(...args){previousGo(...args);report()};
addEventListener('message',event=>{if(event.origin!==location.origin||event.source!==parent)return;const value=event.data;if(value?.type==='slides-navigate'&&Number.isInteger(value.index))go(value.index);if(value?.type==='slides-request-position')report()});
addEventListener('hashchange',report);setInterval(report,2000);report();
})();
