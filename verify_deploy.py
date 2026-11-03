"""Verify an incremental release against a fixed score histogram and immutable prior reports."""
from pathlib import Path
from collections import Counter
from urllib.parse import urlsplit,unquote
import hashlib,html,json,re,sys

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def verify(site,manifest):
 files={p.relative_to(site).as_posix():p for p in site.rglob('*') if p.is_file()}
 assert set(files)==set(manifest['files']),'Release inventory mismatch'
 for name,path in files.items():
  assert not path.is_symlink() and '..' not in Path(name).parts
  assert not re.search(r'private|sqlite|__pycache__|node_modules|\.env',name,re.I)
  proof=manifest['files'][name];assert path.stat().st_size==proof['bytes'] and digest(path)==proof['sha256'],name+': checksum mismatch'
 for name,proof in manifest['immutablePreviousReportFiles'].items():
  assert name in files and files[name].stat().st_size==proof['bytes'] and digest(files[name])==proof['sha256'],name+': previously published report changed'
 refs=manifest['referenceScoresByLevel'];assert manifest['referenceCounts']=={'1-2':118,'3-4':135,'5-6':26}
 for level,rows in refs.items():
  assert len({r['score'] for r in rows})==len(rows) and all(r['count']>0 for r in rows)
  assert sum(r['count'] for r in rows)==manifest['referenceCounts'][level]
 report_map={};lookups=sorted((site/'reports').glob('*.json'));new=set(manifest['newReportKeys'])
 for path in lookups:
  student=json.loads(path.read_text());assert set(student)=={'schemaVersion','reportType','studentNumber','reports'}
  assert student['schemaVersion']==3 and student['reportType']=='mk-mock-report' and re.fullmatch(r'\d{12}',student['studentNumber'])
  token=hashlib.sha256(('mk-mock1:'+student['studentNumber']).encode()).hexdigest()[:32];assert token==path.stem
  assert len({r['level'] for r in student['reports']})==len(student['reports'])
  for report in student['reports']:
   assert set(report)=={'level','score','maximum','rank','percentile','cohortSize','htmlPath','pdfPath'}
   level=report['level'];score=report['score'];assert level in refs and type(score) is int and 0<=score<=report['maximum']
   key=token+'-'+level;assert report['htmlPath']==key+'.html' and report['pdfPath']=='pdfs/'+key+'.pdf'
   assert report['maximum']==(120 if level=='5-6' else 96)
   assert report['htmlPath'] in files and report['pdfPath'] in files and files[report['pdfPath']].read_bytes().startswith(b'%PDF-')
   n=manifest['referenceCounts'][level];rank=1+sum(r['score']>score for r in refs[level]);pr=100*sum(r['count'] for r in refs[level] if r['score']<score)/n
   assert report['rank']==rank and report['cohortSize']==n and abs(report['percentile']-pr)<1e-10,(key,'reference-rank/PR mismatch')
   text=files[report['htmlPath']].read_text();overview=re.search(r'<section id="overview".*?</section>',text,re.S).group()
   cells=[html.unescape(re.sub(r'<[^>]+>','',c)).strip() for c in re.findall(r'<td>(.*?)</td>',overview,re.S)]
   assert cells[-2:]==[str(rank),f'{pr:.1f}'] and f'{n} participants' in overview
   if key in new:
    assert f'fixed October 30, 2026 Level {level.replace("-", "–")} reference cohort ({n} participants)' in overview and 'reference-cohort students' in overview
    assert len(re.findall(r'data-mock-report-key=',text))==1 and f'data-mock-report-key="{key}"' in text
   assert report['pdfPath'] in text and 'OFFLINE BASELINE DEMO' not in text
   for value in re.findall(r'(?:href|src)="([^"]+)"',text):
    parsed=urlsplit(html.unescape(value))
    if parsed.scheme or parsed.netloc or not parsed.path:continue
    relative=unquote(parsed.path);assert relative in files,(key,'missing linked asset',relative)
   assert key not in report_map;report_map[key]=report
 for old in manifest['previousLookupReports']:
  key=old['token']+'-'+old['report']['level'];assert report_map.get(key)==old['report'],(key,'previous lookup payload changed')
 assert new<=set(report_map) and len(lookups)==manifest['students'] and len(report_map)==manifest['reports']
 assert dict(Counter(r['level'] for r in report_map.values()))==manifest['reportsByLevel']
 assert len(list((site/'pdfs').glob('*.pdf')))==manifest['reports']
 assert 'student-number' in files['index.html'].read_text() and 'report-catalog' not in files['index.html'].read_text()
 return {'passed':True,'students':len(lookups),'reports':len(report_map),'newReports':len(new),'immutablePriorReportFiles':len(manifest['immutablePreviousReportFiles']),'referenceCounts':manifest['referenceCounts'],'files':len(files),'rankingBasis':'fixed October30 reference; old reports never reranked'}

if __name__=='__main__':
 assert len(sys.argv)==3,'Usage: verify_incremental_deploy.py SITE MANIFEST'
 print(json.dumps(verify(Path(sys.argv[1]),json.loads(Path(sys.argv[2]).read_text())),ensure_ascii=False))
