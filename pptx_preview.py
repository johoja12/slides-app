"""On-demand local PPTX previews. Source files stay read-only; cache lives in /state."""
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

CACHE=Path(os.environ.get('PPTX_CACHE','/state/pptx'))
POOL=ThreadPoolExecutor(max_workers=1,thread_name_prefix='pptx')
PENDING=set()
MUTEX=threading.Lock()

@lru_cache(maxsize=256)
def _digest(path,mtime,size,inode):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def cache_dir(path):
    stat=path.stat()
    digest=_digest(str(path),stat.st_mtime_ns,stat.st_size,stat.st_ino)
    return CACHE/('v1-'+digest)

def _save(path,value):
    temp=path.with_suffix('.tmp-'+str(os.getpid()))
    temp.write_text(json.dumps(value));temp.replace(path)

def _render(path,directory):
    try:
        directory.mkdir(parents=True,exist_ok=True)
        with open(directory/'lock','a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return
            if (directory/'manifest.json').exists():return
            try:
                if path.stat().st_size>200*1024*1024:raise ValueError('File too large')
                with zipfile.ZipFile(path) as archive:
                    info=archive.infolist()
                    if len(info)>20000 or sum(i.file_size for i in info)>1024**3 or 'ppt/presentation.xml' not in archive.namelist():
                        raise ValueError('Unsupported presentation')
                with tempfile.TemporaryDirectory(prefix='pptx-') as work:
                    work=Path(work);source=work/'source.pptx';shutil.copyfile(path,source)
                    if 'v1-'+hashlib.sha256(source.read_bytes()).hexdigest()!=directory.name:
                        raise ValueError('Source changed')
                    profile=work/'profile'
                    subprocess.run(['libreoffice','-env:UserInstallation='+profile.as_uri(),'--headless','--nologo','--nodefault','--nofirststartwizard','--convert-to','pdf:impress_pdf_Export','--outdir',str(work),str(source)],check=True,timeout=150,capture_output=True)
                    pdf=work/'source.pdf'
                    output=subprocess.run(['pdfinfo',str(pdf)],check=True,timeout=10,capture_output=True,text=True).stdout
                    pages=int(re.search(r'^Pages:\s+(\d+)',output,re.M).group(1))
                    if not 1<=pages<=500:raise ValueError('Too many slides')
                    subprocess.run(['pdftoppm','-jpeg','-jpegopt','quality=85','-scale-to','1600',str(pdf),str(work/'page')],check=True,timeout=180,capture_output=True)
                    rendered=sorted(work.glob('page-*.jpg'),key=lambda p:int(p.stem.split('-')[-1]))
                    if len(rendered)!=pages:raise ValueError('Incomplete render')
                    for i,image in enumerate(rendered,1):shutil.copyfile(image,directory/f'page-{i}.jpg')
                    shutil.copyfile(pdf,directory/'document.pdf')
                    _save(directory/'manifest.json',{'status':'ready','pages':pages})
            except Exception:
                _save(directory/'error.json',{'status':'error','message':'This PowerPoint could not be previewed. You can still download the original file.'})
    finally:
        with MUTEX:PENDING.discard(str(directory))

def status(path):
    directory=cache_dir(path)
    for filename in ['manifest.json','error.json']:
        file=directory/filename
        if file.exists():return json.loads(file.read_text())
    with MUTEX:
        if str(directory) not in PENDING:
            PENDING.add(str(directory));POOL.submit(_render,path,directory)
    return {'status':'processing'}
