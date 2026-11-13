"""Native PowerPoint animation adapter; originals and unmodified ZIP parts stay intact.

Timing tree construction follows PresentationML and pptx-motion-lite (MIT).
See third_party/pptx-motion-lite-LICENSE.txt. No HTML/JavaScript is executed.
"""
from __future__ import annotations
import argparse
import hashlib
from html.parser import HTMLParser
from io import BytesIO
import json
import math
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import tempfile
import threading
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr
import zipfile

NS = {'p':'http://schemas.openxmlformats.org/presentationml/2006/main', 'a':'http://schemas.openxmlformats.org/drawingml/2006/main', 'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
EFFECTS = ('appear','disappear','fade-in','fade-out','wipe-in','fly-in','zoom-in','move','scale')
TRIGGERS = ('click','with','after')
LIMIT = 100*1024*1024
XML_LIMIT = 8*1024*1024
SERIALIZE_LOCK = threading.Lock()
VERSION = 1

class MotionError(ValueError):
    pass


def q(name):
    prefix, local = name.split(':')
    return '{'+NS[prefix]+'}'+local


def sub(parent, name, **attrs):
    return ET.SubElement(parent,q(name),{key:str(value) for key,value in attrs.items()})


def parse_xml(raw):
    if len(raw)>XML_LIMIT or b'\x00' in raw or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise MotionError('Unsupported or oversized XML part.')
    try:
        declarations={}
        depth=0
        for event,value in ET.iterparse(BytesIO(raw),events=['start-ns','start','end']):
            if event=='start':
                depth+=1
                if depth>128:raise MotionError('XML nesting exceeds the supported limit.')
                continue
            if event=='end':depth-=1;continue
            prefix,uri=value
            if prefix in NS and uri!=NS[prefix]:raise MotionError('Reserved Office namespace prefixes cannot be rebound.')
            if prefix in declarations and declarations[prefix]!=uri:
                raise MotionError('Rebound XML namespace prefixes are not supported.')
            declarations[prefix]=uri
        return ET.fromstring(raw),declarations
    except ET.ParseError:
        raise MotionError('The presentation contains malformed XML.') from None


def serialize(root,declarations):
    # Preserve namespace declarations referenced only by mc:Ignorable/Requires values.
    with SERIALIZE_LOCK:
        for prefix,uri in {**declarations,**NS}.items():
            if not re.fullmatch(r'ns\d+',prefix):ET.register_namespace(prefix,uri)
        raw=ET.tostring(root,encoding='utf-8',xml_declaration=True)
    start=raw.index(b'<',raw.index(b'?>')+2)
    end=raw.index(b'>',start)
    opening=raw[start:end]
    extra=[]
    for prefix,uri in declarations.items():
        attr=('xmlns:'+prefix if prefix else 'xmlns').encode()
        if not re.search(rb'\s'+re.escape(attr)+rb'=',opening):
            extra.append(b' '+attr+b'='+quoteattr(uri).encode())
    return raw[:end]+b''.join(extra)+raw[end:]


def plain_text(shape):
    return ' '.join(''.join(shape.itertext()).split()) if shape.tag==q('a:t') else ' '.join(' '.join(node.text or '' for node in shape.iter(q('a:t'))).split())


class Document:
    def __init__(self,source):
        self.source=Path(source)
        if self.source.is_symlink() or not self.source.is_file() or self.source.stat().st_size>LIMIT:
            raise MotionError('Choose a regular PPTX file of at most 100 MB.')
        self.raw=self.source.read_bytes()
        self.sha256=hashlib.sha256(self.raw).hexdigest()
        try:
            self.archive=zipfile.ZipFile(BytesIO(self.raw))
            info=self.archive.infolist()
            names=[item.filename for item in info]
            if len(names)!=len(set(names)) or len(names)>20000 or sum(item.file_size for item in info)>300*1024*1024:
                raise MotionError('The PPTX package exceeds the safety limits or contains duplicates.')
            for item in info:
                parts=PurePosixPath(item.filename).parts
                if item.filename.startswith('/') or '\\' in item.filename or '..' in parts or item.flag_bits&1 or item.file_size>LIMIT or item.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):
                    raise MotionError('The PPTX package contains an unsafe member.')
                if item.filename.casefold().startswith('_xmlsignatures/') or 'vbaproject' in item.filename.casefold():
                    raise MotionError('Signed or macro-enabled presentations cannot be modified by this adapter.')
            content_types,_=parse_xml(self.archive.read('[Content_Types].xml'))
            if any('macroenabled' in node.get('ContentType','').casefold() or 'vba' in node.get('ContentType','').casefold() for node in content_types):
                raise MotionError('Macro-enabled presentations cannot be modified by this adapter.')
            presentation,_=parse_xml(self.archive.read('ppt/presentation.xml'))
            relationships,_=parse_xml(self.archive.read('ppt/_rels/presentation.xml.rels'))
            size=presentation.find('p:sldSz',NS)
            self.size=(int(size.get('cx')),int(size.get('cy')))
            if not all(value>0 for value in self.size):raise MotionError('Invalid slide dimensions.')
            targets={}
            for item in relationships:
                if not item.get('Type','').endswith('/slide'):continue
                target=unquote(item.get('Target',''))
                if item.get('TargetMode')=='External' or urlsplit(target).scheme or '\\' in target:
                    raise MotionError('External slide relationships are not supported.')
                part=posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('ppt',target))
                if not part.startswith('ppt/slides/') or not part.endswith('.xml') or item.get('Id') in targets:
                    raise MotionError('Invalid slide relationship.')
                targets[item.get('Id')]=part
            self.slides=[]
            for number,slide_id in enumerate(presentation.findall('p:sldIdLst/p:sldId',NS),1):
                if number>500:raise MotionError('Presentations are limited to 500 slides.')
                part=targets[slide_id.get(q('r:id'))]
                root,declarations=parse_xml(self.archive.read(part))
                shapes=[]
                tree=root.find('p:cSld/p:spTree',NS)
                seen=set()
                def visit(parent,parent_id=None):
                    for node in parent:
                        if node.tag not in {q('p:'+name) for name in ('sp','pic','graphicFrame','cxnSp','grpSp')}:continue
                        properties=next((child for child in node if child.tag.rsplit('}',1)[-1].startswith('nv')),None)
                        identity=properties.find('p:cNvPr',NS) if properties is not None else None
                        if identity is None:continue
                        sid=int(identity.get('id'))
                        if sid<1 or sid in seen:raise MotionError('Duplicate or invalid shape IDs.')
                        seen.add(sid)
                        shapes.append({'id':sid,'name':identity.get('name',''),'text':plain_text(node),'type':node.tag.rsplit('}',1)[-1],'parent_id':parent_id,'has_text':node.find('p:txBody',NS) is not None})
                        if node.tag==q('p:grpSp'):visit(node,sid)
                if tree is None:raise MotionError('A slide is missing its shape tree.')
                visit(tree)
                if len(shapes)>5000:raise MotionError('A slide contains too many objects.')
                if sum(len(item['shapes']) for item in self.slides)+len(shapes)>20000:raise MotionError('The presentation contains too many objects.')
                self.slides.append({'number':number,'part':part,'root':root,'namespaces':declarations,'shapes':shapes,'has_animation':root.find('p:timing',NS) is not None})
            if not self.slides:raise MotionError('The PPTX has no slides.')
        except MotionError:
            raise
        except (OSError,ValueError,KeyError,TypeError,AttributeError,zipfile.BadZipFile,RuntimeError):
            raise MotionError('This PPTX package could not be inspected.') from None

    def inventory(self):
        return {'source_sha256':self.sha256,'slides':[{'number':slide['number'],'has_animation':slide['has_animation'],'shapes':[{**shape,'text':shape['text'][:400]} for shape in slide['shapes']]} for slide in self.slides]}

    def resolve(self,number,target):
        if type(number) is not int or not 1<=number<=len(self.slides):raise MotionError('Animation slide number is out of range.')
        if not isinstance(target,dict) or len(target)!=1 or next(iter(target)) not in ('id','name','text'):
            raise MotionError('An animation target needs exactly one shape ID, name or exact text selector.')
        key,value=next(iter(target.items()))
        if key=='id' and type(value) is not int:raise MotionError('Shape IDs must be integers.')
        if key!='id' and (not isinstance(value,str) or not value or len(value)>2000):raise MotionError('Invalid shape selector.')
        found=[shape for shape in self.slides[number-1]['shapes'] if shape[key]==value]
        if len(found)!=1:raise MotionError('An animation target is missing or ambiguous. Use its exact slide and shape ID.')
        return found[0]


def bounded_number(value,low,high,label):
    if type(value) not in (int,float) or not low<=value<=high or not math.isfinite(value):
        raise MotionError(label+' is out of range.')
    return value


def validate(doc,plan):
    if not isinstance(plan,dict) or set(plan)-{'version','source_sha256','steps','replace_existing'} or type(plan.get('version')) is not int or plan.get('version')!=1:
        raise MotionError('Use an animation plan with version 1 and supported fields.')
    if plan.get('source_sha256')!=doc.sha256:raise MotionError('The source PPTX changed. Reload the object map before exporting.')
    if type(plan.get('replace_existing',False)) is not bool:raise MotionError('replace_existing must be a boolean.')
    steps=plan.get('steps')
    if not isinstance(steps,list) or not 1<=len(steps)<=1000:raise MotionError('Choose between 1 and 1,000 animation steps.')
    normalized=[]
    for step in steps:
        if not isinstance(step,dict) or set(step)-{'slide','target','effect','trigger','duration_ms','delay_ms','path','scale','direction','object'}:
            raise MotionError('An animation step contains unsupported fields.')
        effect=step.get('effect')
        if effect not in EFFECTS:raise MotionError('Unsupported animation effect; no silent replacement was made.')
        trigger=step.get('trigger','click')
        if trigger not in TRIGGERS:raise MotionError('Use click, with or after for the animation trigger.')
        shape=doc.resolve(step.get('slide'),step.get('target'))
        duration=int(bounded_number(step.get('duration_ms',600),1,60000,'Duration'))
        delay=int(bounded_number(step.get('delay_ms',0),0,60000,'Delay'))
        value={'slide':step['slide'],'target':{'id':shape['id']},'effect':effect,'trigger':trigger,'duration_ms':duration,'delay_ms':delay}
        if effect=='move':
            path=step.get('path')
            if not isinstance(path,list) or not 2<=len(path)<=64:raise MotionError('A motion path needs 2–64 points in slide-relative coordinates.')
            if path[0]!=[0,0]:raise MotionError('Motion paths must start at [0, 0], relative to the object position.')
            for point in path:
                if not isinstance(point,list) or len(point)!=2:raise MotionError('Motion path points need x and y coordinates.')
                for coordinate in point:bounded_number(coordinate,-2,2,'Motion coordinate')
            value['path']=path
        elif 'path' in step:raise MotionError('Only move effects accept motion paths.')
        if effect=='scale':
            scale=step.get('scale')
            if not isinstance(scale,list) or len(scale)!=2:raise MotionError('Scaling needs [width, height] multipliers.')
            for factor in scale:bounded_number(factor,.01,10,'Scale')
            value['scale']=scale
        elif 'scale' in step:raise MotionError('Only scale effects accept scale multipliers.')
        if effect in ('fly-in','wipe-in'):
            direction=step.get('direction','right')
            if direction not in ('left','right','up','down'):raise MotionError('Unsupported animation direction.')
            value['direction']=direction
        elif 'direction' in step:raise MotionError('This effect does not accept a direction.')
        if doc.slides[step['slide']-1]['has_animation'] and not plan.get('replace_existing',False):
            raise MotionError('A selected slide already has animations. Explicitly enable replacing its timeline first.')
        normalized.append(value)
    return {'version':1,'source_sha256':doc.sha256,'steps':normalized,'replace_existing':plan.get('replace_existing',False)}


class Timeline:
    def __init__(self):self.next_id=1
    def ctn(self,parent,**attrs):
        value=sub(parent,'p:cTn',id=self.next_id,**attrs);self.next_id+=1;return value
    def condition(self,parent,delay):sub(sub(parent,'p:stCondLst'),'p:cond',delay=delay)
    def behavior(self,parent,sid,duration):
        common=sub(parent,'p:cBhvr');self.ctn(common,dur=duration,fill='hold');sub(sub(common,'p:tgtEl'),'p:spTgt',spid=sid);return common
    def visibility(self,parent,sid,visible,delay=0):
        node=sub(parent,'p:set');common=self.behavior(node,sid,1);self.condition(common.find('p:cTn',NS),delay)
        sub(sub(common,'p:attrNameLst'),'p:attrName').text='style.visibility';sub(sub(node,'p:to'),'p:strVal',val='visible' if visible else 'hidden')
    def effect(self,parent,step):
        sid=step['target']['id'];duration=step['duration_ms'];effect=step['effect']
        entering=effect in ('appear','fade-in','wipe-in','fly-in','zoom-in')
        if entering:self.visibility(parent,sid,True)
        if effect=='disappear':self.visibility(parent,sid,False)
        elif effect in ('fade-in','fade-out','wipe-in'):
            name='fade' if effect.startswith('fade') else 'wipe('+{'right':'right','left':'left','up':'up','down':'down'}[step['direction']]+')'
            node=sub(parent,'p:animEffect',transition='out' if effect=='fade-out' else 'in',filter=name);self.behavior(node,sid,duration)
            if effect=='fade-out':self.visibility(parent,sid,False,duration-1)
        elif effect=='move':
            points=step['path'];path='M '+str(points[0][0])+' '+str(points[0][1])+' '+' '.join('L '+str(x)+' '+str(y) for x,y in points[1:])+' E'
            node=sub(parent,'p:animMotion',origin='layout',path=path,pathEditMode='relative',rAng=0);self.behavior(node,sid,duration)
        elif effect in ('scale','zoom-in'):
            node=sub(parent,'p:animScale',zoomContents='1');self.behavior(node,sid,duration)
            sub(node,'p:from',x=0 if effect=='zoom-in' else 100000,y=0 if effect=='zoom-in' else 100000)
            scale=step.get('scale',[1,1]);sub(node,'p:to',x=round(scale[0]*100000),y=round(scale[1]*100000))
        elif effect=='fly-in':
            direction=step['direction'];axis='ppt_x' if direction in ('left','right') else 'ppt_y'
            start='-#ppt_w/2' if direction=='right' else '1+#ppt_w/2' if direction=='left' else '-#ppt_h/2' if direction=='down' else '1+#ppt_h/2'
            node=sub(parent,'p:anim',calcmode='lin',valueType='num');common=self.behavior(node,sid,duration)
            sub(sub(common,'p:attrNameLst'),'p:attrName').text=axis
            values=sub(node,'p:tavLst')
            for moment,formula in ((0,start),(100000,'#'+axis)):
                sub(sub(sub(values,'p:tav',tm=moment),'p:val'),'p:strVal',val=formula)
    def build(self,steps,shapes):
        timing=ET.Element(q('p:timing'));root=self.ctn(sub(sub(timing,'p:tnLst'),'p:par'),dur='indefinite',restart='never',nodeType='tmRoot')
        sequence=sub(sub(root,'p:childTnLst'),'p:seq',concurrent=1,nextAc='seek')
        main=self.ctn(sequence,dur='indefinite',nodeType='mainSeq');main_children=sub(main,'p:childTnLst')
        outer=None;inner=None;elapsed=0;parallel_end=0
        for step in steps:
            trigger=step['trigger']
            if trigger=='click' or outer is None:
                outer=self.ctn(sub(main_children,'p:par'),fill='hold');self.condition(outer,'indefinite' if trigger=='click' else 0)
                outer_children=sub(outer,'p:childTnLst');elapsed=0;parallel_end=0;inner=None
            if trigger!='with' or inner is None:
                if trigger=='after':elapsed=parallel_end
                wrapper=self.ctn(sub(outer_children,'p:par'),fill='hold');self.condition(wrapper,elapsed);inner=sub(wrapper,'p:childTnLst')
            effect=step['effect'];preset_class='exit' if effect in ('fade-out','disappear') else 'path' if effect=='move' else 'emph' if effect=='scale' else 'entr'
            preset={'appear':1,'disappear':1,'fade-in':10,'fade-out':10,'wipe-in':22,'fly-in':2,'zoom-in':53,'move':0,'scale':6}[effect]
            leaf=self.ctn(sub(inner,'p:par'),presetID=preset,presetClass=preset_class,presetSubtype=0,fill='hold',nodeType={'click':'clickEffect','with':'withEffect','after':'afterEffect'}[trigger])
            self.condition(leaf,step['delay_ms']);self.effect(sub(leaf,'p:childTnLst'),step)
            parallel_end=max(parallel_end,elapsed+step['delay_ms']+step['duration_ms'])
        for name,event in (('prevCondLst','onPrev'),('nextCondLst','onNext')):
            cond=sub(sub(sequence,'p:'+name),'p:cond',evt=event,delay=0);sub(sub(cond,'p:tgtEl'),'p:sldTgt')
        text_ids={shape['id'] for shape in shapes if shape['has_text']}
        targets=sorted({step['target']['id'] for step in steps}&text_ids)
        if targets:
            builds=sub(timing,'p:bldLst')
            for sid in targets:sub(builds,'p:bldP',spid=sid,grpId=0,animBg=1)
        return timing


def apply(source,output,plan):
    source=Path(source);output=Path(output)
    if source.resolve()==output.resolve() or output.is_symlink():raise MotionError('Animated output must be a separate regular file.')
    doc=Document(source);plan=validate(doc,plan)
    changed={}
    for slide in doc.slides:
        steps=[step for step in plan['steps'] if step['slide']==slide['number']]
        if not steps:continue
        root=slide['root']
        for existing in list(root):
            if existing.tag==q('p:timing'):root.remove(existing)
        timing=Timeline().build(steps,slide['shapes'])
        ext=root.find('p:extLst',NS)
        root.insert(list(root).index(ext) if ext is not None else len(root),timing)
        changed[slide['part']]=serialize(root,slide['namespaces'])
    output.parent.mkdir(parents=True,exist_ok=True)
    handle,temp=tempfile.mkstemp(prefix='motion-',suffix='.pptx',dir=output.parent);os.close(handle)
    try:
        with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_DEFLATED) as target:
            for item in doc.archive.infolist():target.writestr(item,changed.get(item.filename,doc.archive.read(item)))
        with zipfile.ZipFile(temp) as check:
            if check.testzip():raise MotionError('Output integrity check failed.')
            for part in changed:
                tree,_=parse_xml(check.read(part));timing=tree.find('p:timing',NS)
                ids=[node.get('id') for node in timing.iter(q('p:cTn'))]
                if len(ids)!=len(set(ids)):raise MotionError('Duplicate animation timing IDs.')
        os.replace(temp,output)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return {'animated_slides':len(changed),'steps':len(plan['steps']),'source_sha256':doc.sha256}


class Instructions(HTMLParser):
    """Only declarative annotations/JSON are read. Scripts and styles are never executed."""
    def __init__(self,source_sha256,single_slide):
        super().__init__();self.sha=source_sha256;self.single=single_slide;self.stack=[];self.steps=[];self.issues=[];self.capture=False;self.json=[];self.inline=None;self.canvas=False;self.blocks=0
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='canvas':self.canvas=True
        if tag=='script' and attrs.get('type')=='application/json' and attrs.get('id')=='pptx-animations':self.blocks+=1;self.json=[];self.capture=True;return
        slide=attrs.get('data-pptx-slide') or (self.stack[-1][1] if self.stack else None)
        if tag not in ('img','br','hr','meta','link','input','source','wbr','area','base','embed','param','track','col'):self.stack.append((tag,slide))
        name=attrs.get('data-pptx-animation')
        known={'fade-in','fade-out','appear','disappear','wipe-in','fly-in','zoom-in'}
        if not name:name=next((value for value in attrs.get('class','').split() if value in known),None)
        if not name:return
        try:
            number=int(slide) if slide else 1 if self.single else None
            if number is None:raise MotionError('An animated HTML element needs data-pptx-slide for a multi-slide deck.')
            target={'name':attrs['data-pptx-shape']} if attrs.get('data-pptx-shape') else {'text':attrs['data-pptx-text']} if attrs.get('data-pptx-text') else None
            if not target:raise MotionError('An animated HTML element needs data-pptx-shape or data-pptx-text to map to an editable object.')
            def milliseconds(key,default):
                raw=attrs.get(key,str(default));match=re.fullmatch(r'(\d+(?:\.\d+)?)(ms|s)?',raw)
                if not match:raise MotionError('HTML animation timing must be a finite number in ms or seconds.')
                return round(float(match[1])*(1000 if match[2]=='s' else 1))
            step={'slide':number,'target':target,'effect':name,'trigger':attrs.get('data-pptx-animation-start','click'),'duration_ms':milliseconds('data-pptx-animation-duration',600),'delay_ms':milliseconds('data-pptx-animation-delay',0)}
            if name in ('fly-in','wipe-in'):step['direction']=attrs.get('data-pptx-animation-direction','right')
            if name=='move':step['path']=json.loads(attrs.get('data-pptx-path','null'))
            if name=='scale':step['scale']=json.loads(attrs.get('data-pptx-scale','null'))
            self.steps.append(step)
        except (ValueError,MotionError,RecursionError,OverflowError) as error:self.issues.append(str(error))
    def handle_endtag(self,tag):
        if tag=='script' and self.capture:
            self.capture=False
            try:self.inline=json.loads(''.join(self.json))
            except (ValueError,RecursionError):self.issues.append('The pptx-animations JSON block is malformed or too deeply nested.')
        for index in range(len(self.stack)-1,-1,-1):
            if self.stack[index][0]==tag:self.stack=self.stack[:index];break
    def handle_data(self,value):
        if self.capture:self.json.append(value)


def from_html(html,doc):
    if len(html.encode())>XML_LIMIT:raise MotionError('HTML instructions exceed 8 MB.')
    parser=Instructions(doc.sha256,len(doc.slides)==1);parser.feed(html)
    if parser.blocks>1:parser.issues.append('Use only one pptx-animations JSON block.')
    if parser.capture:parser.issues.append('The pptx-animations JSON block is incomplete.')
    if parser.inline is not None and parser.steps:parser.issues.append('Use either inline JSON or element annotations, not both.')
    plan=parser.inline if parser.inline is not None else {'version':1,'source_sha256':doc.sha256,'steps':parser.steps,'replace_existing':False}
    if not isinstance(plan,dict):parser.issues.append('The animation manifest must be a JSON object.')
    if isinstance(plan,dict) and 'source_sha256' not in plan:
        # Stable semantic selectors can be rebound during each static export; numeric IDs cannot.
        steps=plan.get('steps',[])
        if not isinstance(steps,list):
            parser.issues.append('Animation steps must be an array.');steps=[]
        if any(isinstance(step,dict) and isinstance(step.get('target'),dict) and 'id' in step['target'] for step in steps):
            parser.issues.append('Numeric shape bindings require an explicit source_sha256.')
        else:plan={**plan,'source_sha256':doc.sha256}
    if not parser.issues and isinstance(plan,dict) and (plan.get('steps') or parser.blocks):
        try:plan=validate(doc,plan)
        except MotionError as error:parser.issues.append(str(error))
    warnings=[]
    if parser.canvas:warnings.append('Canvas drawings need explicit per-object bindings and timeline steps. Their JavaScript motion is not inferred.')
    if not parser.steps and parser.inline is None:warnings.append('No declarative animation instructions found. Add mapped steps or annotate the HTML source.')
    return plan,parser.issues,warnings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--inspect',action='store_true');parser.add_argument('--manifest',type=Path);parser.add_argument('--html',type=Path);parser.add_argument('-o','--output',type=Path)
    args=parser.parse_args()
    try:
        doc=Document(args.source)
        if args.inspect:print(json.dumps(doc.inventory(),ensure_ascii=False,indent=2));return
        if bool(args.manifest)==bool(args.html) or not args.output:raise MotionError('Choose exactly one --manifest or --html input and a separate --output.')
        if args.html:
            plan,issues,warnings=from_html(args.html.read_text(),doc)
            if issues:raise MotionError(' '.join(issues))
            for warning in warnings:print(warning,file=__import__('sys').stderr)
        else:
            if args.manifest.stat().st_size>1024*1024:raise MotionError('Manifest exceeds 1 MB.')
            plan=json.loads(args.manifest.read_text())
        print(json.dumps(apply(args.source,args.output,plan)))
    except (MotionError,OSError,ValueError,RecursionError) as error:
        parser.exit(2,'Animation export failed: '+str(error)+'\n')

if __name__=='__main__':main()
