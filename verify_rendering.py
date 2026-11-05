"""Real LibreOffice/Poppler acceptance test. Run inside the app image, network disabled."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

import library_store
import pptx_preview
import slide_content

with tempfile.TemporaryDirectory(prefix='slides-render-') as temporary:
    work=Path(temporary)
    pptx_preview.CACHE=work/'cache'
    source=work/'synthetic.fodp'
    source.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" office:version="1.3" office:mimetype="application/vnd.oasis.opendocument.presentation"><office:automatic-styles><style:page-layout style:name="pm1"><style:page-layout-properties fo:page-width="28cm" fo:page-height="15.75cm"/></style:page-layout></office:automatic-styles><office:master-styles><draw:master-page draw:name="Default" style:page-layout-name="pm1"/></office:master-styles><office:body><office:presentation><draw:page draw:name="First" draw:master-page-name="Default"><draw:frame svg:x="2cm" svg:y="2cm" svg:width="23cm" svg:height="5cm"><draw:text-box><text:p>Galactic coffee first slide</text:p></draw:text-box></draw:frame></draw:page><draw:page draw:name="Second" draw:master-page-name="Default"><draw:frame svg:x="2cm" svg:y="2cm" svg:width="23cm" svg:height="5cm"><draw:text-box><text:p>Arabica constellation second slide</text:p></draw:text-box></draw:frame></draw:page></office:presentation></office:body></office:document>''')
    subprocess.run(['libreoffice','-env:UserInstallation='+str((work/'profile').as_uri()),'--headless','--convert-to','pptx','--outdir',str(work),str(source)],check=True,timeout=60,capture_output=True)
    pptx=work/'synthetic.pptx'
    assert pptx.is_file()
    original=pptx.read_bytes();modified=pptx.stat().st_mtime_ns
    pages=slide_content.extract(pptx)
    assert len(pages)==2 and 'Galactic coffee' in pages[0][1] and 'Arabica' in pages[1][1], pages
    validation=work/'bundle';validation.mkdir();shutil.copy2(pptx,validation/pptx.name)
    assert library_store.validate(validation,{})['pptx']==pptx.name
    result=pptx_preview.status(pptx)
    deadline=time.monotonic()+90
    while result['status']=='processing' and time.monotonic()<deadline:
        time.sleep(.25);result=pptx_preview.status(pptx)
    assert result['status']=='ready' and result['pages']==2,result
    image,mime,status=slide_content.thumbnail(pptx,work)
    assert mime=='image/jpeg' and status=='ready' and image.read_bytes()[:2]==b'\xff\xd8'
    pdf=work/'synthetic.pdf';shutil.copy2(pptx_preview.cache_dir(pptx)/'document.pdf',pdf)
    text=slide_content.extract(pdf)
    assert len(text)==2 and 'Galactic coffee' in text[0][1] and 'Arabica' in text[1][1],text
    deadline=time.monotonic()+30
    while True:
        image,mime,status=slide_content.thumbnail(pdf,work)
        if status!='processing' or time.monotonic()>deadline:break
        time.sleep(.25)
    assert status=='ready' and mime=='image/jpeg' and image.is_file()
    old_cache=pptx_preview.cache_dir(pdf)
    # Even a same-length replacement with its old mtime must invalidate derived cache.
    data=pdf.read_bytes();pdf.write_bytes(data.replace(b'PDF-',b'PDF_',1));os.utime(pdf,ns=(pdf.stat().st_atime_ns,pdf.stat().st_mtime_ns-1))
    assert pptx_preview.cache_dir(pdf)!=old_cache
    assert pptx.read_bytes()==original and pptx.stat().st_mtime_ns==modified
    print('Real rendering passed: 2-slide PPTX conversion, PDF/PPTX text and page pointers, upload validation, both thumbnails, invalidation and unchanged original')
