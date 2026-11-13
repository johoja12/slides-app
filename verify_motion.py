"""Synthetic native animation acceptance tests; never opens the real library."""
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import runpy
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

import pptx_motion as m


def make_pptx(path):
    """Two synthetic slides, deliberately using relationship order rather than filenames."""
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml','''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/><Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/><Override PartName="/ppt/slides/slide2.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/></Types>''')
        archive.writestr('_rels/.rels','''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>''')
        archive.writestr('ppt/presentation.xml',f'''<p:presentation xmlns:p="{m.NS['p']}" xmlns:r="{m.NS['r']}"><p:sldIdLst><p:sldId id="256" r:id="r2"/><p:sldId id="257" r:id="r1"/></p:sldIdLst><p:sldSz cx="12192000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>''')
        archive.writestr('ppt/_rels/presentation.xml.rels','''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/><Relationship Id="r2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide2.xml"/></Relationships>''')
        for index in (1,2):
            objects=''.join(f'''<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="{name}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="100000" y="{sid*200000}"/><a:ext cx="5000000" cy="400000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="en-US"/><a:t>{text}</a:t></a:r></a:p></p:txBody></p:sp>''' for sid,name,text in ((2,'Heading',f'Synthetic slide {index}'),(3,'Body','Coffee beans'),(4,'Duplicate','Coffee beans')))
            archive.writestr(f'ppt/slides/slide{index}.xml',f'''<p:sld xmlns:p="{m.NS['p']}" xmlns:a="{m.NS['a']}" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main" mc:Ignorable="p14"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>{objects}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr><p:extLst/></p:sld>''')
        archive.writestr('ppt/media/unchanged.bin',b'synthetic media\x00')
    return path


def base_plan(doc,steps=None):
    return {'version':1,'source_sha256':doc.sha256,'steps':steps or [{'slide':1,'target':{'name':'Heading'},'effect':'fade-in','trigger':'click','duration_ms':600,'delay_ms':0}],'replace_existing':False}


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.source=make_pptx(Path(self.temp.name)/'input.pptx');self.doc=m.Document(self.source)
    def rejects(self,plan):
        with self.assertRaises(m.MotionError):m.validate(self.doc,plan)
    def test_inventory_selectors_and_source_guard(self):
        self.assertEqual(self.doc.slides[0]['part'],'ppt/slides/slide2.xml')
        self.assertEqual(self.doc.resolve(1,{'text':'Synthetic slide 2'})['id'],2)
        for target in ({'text':'Coffee beans'},{'name':'absent'},{'id':True},{'id':2,'name':'Heading'}):
            with self.assertRaises(m.MotionError):self.doc.resolve(1,target)
        plan=base_plan(self.doc);plan['source_sha256']='0'*64;self.rejects(plan)
        plan=base_plan(self.doc);plan['version']=True;self.rejects(plan)
        plan=base_plan(self.doc);plan['steps'][0]['duration_ms']=10**1000;self.rejects(plan)
        plan=base_plan(self.doc);plan['steps'][0]['delay_ms']=float('nan');self.rejects(plan)
        for effect in ('spin-forever','javascript',''):
            plan=base_plan(self.doc);plan['steps'][0]['effect']=effect;self.rejects(plan)
        for path in ([[1,0],[0,0]],[[0,0],[3,0]],[[0,0],[float('inf'),0]]):
            plan=base_plan(self.doc);plan['steps'][0].update(effect='move',path=path);self.rejects(plan)
    def test_all_effects_preserve_static_parts_and_namespaces(self):
        steps=[]
        for index,effect in enumerate(m.EFFECTS):
            step={'slide':1,'target':{'id':2+index%3},'effect':effect,'trigger':('click','with','after')[index%3],'duration_ms':700,'delay_ms':100}
            if effect=='move':step['path']=[[0,0],[.2,.1],[.4,0]]
            if effect=='scale':step['scale']=[1.5,2]
            if effect in ('fly-in','wipe-in'):step['direction']='right'
            steps.append(step)
        output=Path(self.temp.name)/'output.pptx';original=self.source.read_bytes();mtime=self.source.stat().st_mtime_ns
        result=m.apply(self.source,output,base_plan(self.doc,steps));self.assertEqual(result['steps'],9)
        with zipfile.ZipFile(output) as archive:
            for name in self.doc.archive.namelist():
                if name!='ppt/slides/slide2.xml':self.assertEqual(archive.read(name),self.doc.archive.read(name))
            raw=archive.read('ppt/slides/slide2.xml');self.assertIn(b'xmlns:p14=',raw)
            tree,_=m.parse_xml(raw);old=deepcopy(self.doc.slides[0]['root'])
            timing=tree.find('p:timing',m.NS);tree.remove(timing)
            self.assertEqual(ET.tostring(tree),ET.tostring(old))
            ids=[node.get('id') for node in timing.iter(m.q('p:cTn'))];self.assertEqual(len(ids),len(set(ids)))
            self.assertTrue(all(node.get('spid') in ('2','3','4') for node in timing.iter(m.q('p:spTgt'))))
            self.assertEqual(len(list(timing.iter(m.q('p:animMotion')))),1)
            self.assertEqual(len(list(timing.iter(m.q('p:animScale')))),2)
            self.assertEqual(len(list(timing.iter(m.q('p:animEffect')))),3)
            children=list(m.parse_xml(raw)[0]);self.assertEqual([node.tag for node in children[-2:]],[m.q('p:timing'),m.q('p:extLst')])
        self.assertEqual(self.source.read_bytes(),original);self.assertEqual(self.source.stat().st_mtime_ns,mtime)
        with self.assertRaises(m.MotionError):m.apply(self.source,self.source,base_plan(self.doc))
        animated=m.Document(output)
        with self.assertRaises(m.MotionError):m.validate(animated,base_plan(animated))
        plan=base_plan(animated);plan['replace_existing']=True;m.apply(output,Path(self.temp.name)/'replaced.pptx',plan)
    def test_trigger_schedule(self):
        steps=[]
        for trigger,duration,delay in (('click',600,100),('with',1000,0),('after',200,50),('click',100,0)):
            steps.append({'slide':1,'target':{'id':2},'effect':'fade-in','trigger':trigger,'duration_ms':duration,'delay_ms':delay})
        timing=m.Timeline().build(steps,self.doc.slides[0]['shapes'])
        groups=timing.findall('p:tnLst/p:par/p:cTn/p:childTnLst/p:seq/p:cTn/p:childTnLst/p:par/p:cTn',m.NS)
        self.assertEqual(len(groups),2)
        wrappers=groups[0].findall('p:childTnLst/p:par/p:cTn',m.NS)
        self.assertEqual([node.find('p:stCondLst/p:cond',m.NS).get('delay') for node in wrappers],['0','1000'])
        self.assertEqual(groups[1].find('p:stCondLst/p:cond',m.NS).get('delay'),'indefinite')
    def test_html_contract_never_runs_scripts(self):
        html='<section data-pptx-slide="1"><h1 data-pptx-shape="Heading" data-pptx-animation="fade-in" data-pptx-animation-duration="0.8s">Title</h1><canvas></canvas><script>throw Error("never execute")</script></section>'
        plan,issues,warnings=m.from_html(html,self.doc);self.assertFalse(issues);self.assertEqual(plan['steps'][0]['duration_ms'],800);self.assertTrue(warnings)
        for html in ('<p class="fade-in">unmapped</p>','<script type="application/json" id="pptx-animations">[]</script>', '<script type="application/json" id="pptx-animations">{"version":1,"steps":{}}</script>', '<script type="application/json" id="pptx-animations">{"version":1,"steps":[{"target":{"id":2}}]}</script>'):
            self.assertTrue(m.from_html(html,self.doc)[1],html)
        block='<script type="application/json" id="pptx-animations">'+json.dumps(base_plan(self.doc))+'</script>'
        self.assertTrue(m.from_html(block+block,self.doc)[1]);self.assertFalse(m.from_html(block,self.doc)[1])
    def test_unsafe_xml_and_packages(self):
        for raw in (b'<!DOCTYPE x><x/>',b'<x>\x00</x>',b'<broken>',b'<a xmlns:p="one"><b xmlns:p="two"/></a>'):
            with self.assertRaises(m.MotionError):m.parse_xml(raw)
        for name in ('../escape','_xmlsignatures/sig.xml','ppt/VBAPROJECT.bin'):
            unsafe=Path(self.temp.name)/'unsafe.pptx'
            unsafe.write_bytes(self.source.read_bytes())
            with zipfile.ZipFile(unsafe,'a') as archive:archive.writestr(name,b'unsafe')
            with self.assertRaises(m.MotionError):m.Document(unsafe)


def api_checks():
    fixture=runpy.run_path(str(Path(__file__).with_name('verify.py')))
    mod,root,client,csrf,origin=(fixture[key] for key in ('mod','root','c','csrf','origin'))
    folder=root/'native-motion';folder.mkdir();source=make_pptx(folder/'demo.pptx')
    html=folder/'index.html';html.write_text('<section data-pptx-slide="1"><h1 data-pptx-shape="Heading" data-pptx-animation="fade-in">Synthetic</h1></section>')
    before={path:(path.read_bytes(),path.stat().st_mtime_ns) for path in (source,html)}
    url='/motion/native-motion/demo.pptx';headers={'Accept':'application/json'}
    def get(path=url):return client.get(path,base_url=origin,headers=headers)
    def post(plan,**extra):return client.post(url,base_url=origin,headers=headers,data={'csrf':csrf,'plan':json.dumps(plan),'html_sha256':get().json['html_sha256'],**extra})
    guest=mod.app.test_client();assert guest.get(url,base_url=origin).status_code==302
    response=get();assert response.status_code==200,response.data
    data=response.json;assert len(data['slides'])==2 and len(data['plan']['steps'])==1
    assert client.post(url,base_url=origin,data={'plan':'{}'}).status_code==400
    plan=data['plan'];response=post(plan);assert response.status_code==200,response.data
    with zipfile.ZipFile(BytesIO(response.data)) as archive:assert b'animEffect' in archive.read('ppt/slides/slide2.xml')
    assert 'demo-animated.pptx' in response.headers['Content-Disposition']
    assert get().json['plan']==m.validate(m.Document(source),plan)
    assert post(plan).data==response.data
    assert post(plan,html_sha256='old').status_code==409
    bad=deepcopy(plan);bad['source_sha256']='old';assert post(bad).status_code==422
    bad=deepcopy(plan);bad['steps'][0]['effect']='unsupported';assert post(bad).status_code==422
    assert get('/motion/native-motion/../demo/demo.pptx').status_code==404
    assert get('/motion/native-motion/index.html').status_code==404
    assert all((p.read_bytes(),p.stat().st_mtime_ns)==value for p,value in before.items())
    # Historical mapping stays bound to its own source, not a neighboring revision/deck.
    snapshot=client.post('/history/native-motion',base_url=origin,headers=headers,data={'csrf':csrf,'action':'snapshot','expected':'live'})
    assert snapshot.status_code==302,snapshot.data
    with mod.db() as conn:rid=conn.execute('SELECT r.id FROM revisions r JOIN decks d ON d.id=r.deck_id WHERE d.name=?',('native-motion',)).fetchone()[0]
    historic=get(f'/r/{rid}/motion/native-motion/demo.pptx');assert historic.status_code==200,historic.data
    assert historic.json['source_sha256']==data['source_sha256']
    assert get(f'/r/{rid}/motion/demo/demo.pptx').status_code==404
    print('Native animation API passed: authentication, CSRF, annotations, download/cache, saved plans, stale bindings, revision isolation and unchanged originals')


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeTests))
    if not result.wasSuccessful():raise SystemExit(1)
    api_checks()
