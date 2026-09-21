"""Build a static course gallery from Akari PDF exports. Requires pdftotext (Poppler)."""
from pathlib import Path
import argparse, datetime, hashlib, json, re, shutil, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
CODE=r'(?:PS\d+\s*-\s*Electives\s+\d+|\d{4}\s*-\s*Electives\s+\d+|[A-Z]{2,4}\d{3,4})'
ROW=re.compile(r'^\s*('+CODE+r')\s{2,}(.+?)\s*$')

def extract(path):
 p=subprocess.run(['pdftotext','-layout',str(path),'-'],capture_output=True,text=True,check=True)
 return p.stdout

def intake_routes(text):
 clean=re.sub(r'^Course .*?·.*$|^Page \d+ of \d+\s*$','',text,flags=re.M)
 flat=' '.join(clean.split()); result={}
 for mode,following in [('Full-Time','Part-Time'),('Part-Time','Online Learning')]:
  m=re.search(re.escape(mode)+r' Students(.*?)'+re.escape(following),flat)
  if not m:continue
  result[mode]={}
  for match in re.finditer(r'For (September|January) entry, the sequence of modules will be:\s*(.*?)(?=For (?:September|January) entry|$)',m[1]):
   steps=[];year=1;last=0
   for x in re.finditer(r'Semester (\d+)\s*\(([^)]+)\)',match[2]):
    month=re.search(r'taken in (September|January|May)',x[2])
    if not month:continue
    monthnum={'January':1,'May':5,'September':9}[month[1]]
    if monthnum<last:year+=1
    last=monthnum
    steps.append({'semester':int(x[1]),'month':month[1],'year':year,'project':'project' in x[2].lower(),'spansTwoSemesters':'spanning 2 semesters' in x[2]})
   if steps:result[mode][match[1]]=steps
 return {k:v for k,v in result.items() if v}

def parse(text,filename):
 head=re.search(r'^Course\s+(\d+)\s*-\s*(.*?)\s*·\s*(.+)$',text,re.M)
 if not head:raise ValueError('Course code, title or export date not recognised')
 code,title,date=head.groups(); pg=bool(re.search(r'Course Type\s+Postgraduate',text))
 credit=re.search(r'SCQF Credit Points\s+(\d+)',text)
 if not credit:raise ValueError('Award credit total not found')
 modules=[];current=None;kind='core';seen={};page=1;duplicates=0
 for line in text.split('\n'):
  page+=line.count('\f');line=line.replace('\f','')
  if line.strip()=='Course Deliveries':break
  heading=re.match(r'^\s*Stage\s+(\d+)\s*/\s*Semester\s+(\d+)\s*$',line)
  if heading:current=tuple(map(int,heading.groups()));continue
  if not current:continue
  if line.strip() in ('Core','Elective','Optional'):kind=line.strip().lower();continue
  match=ROW.match(line)
  if not match:continue
  c,rest=match.groups();cols=re.split(r'\s{2,}',rest);name=cols[0].strip()
  if not name:raise ValueError('Empty module title for '+c)
  credits=re.search(r'(?:Yes\s+)?\d+\.\d+\s+(\d+)(?:\s+Level\s+\d+)?\s*$',rest)
  value=int(credits[1]) if credits else None
  group='electives' in c.lower()
  item={'stage':current[0],'semester':current[1],'code':c,'title':name,'credits':value,'type':'elective' if group else kind,'page':page,'additional':False}
  key=(current,c)
  if key in seen:
   old=modules[seen[key]]
   if old['title']!=name or old['credits']!=value:raise ValueError('Conflicting repeated row: '+c)
   duplicates+=1;continue
  seen[key]=len(modules);modules.append(item)
 if not modules:raise ValueError('No stage/semester module rows found; scanned or unsupported PDF')
 warnings=[]
 # This explicit statement and a standalone semester-3 block identify the extra
 # placement/study-abroad slots in the supplied UG delivery-table format.
 exclusion='credits accumulated do not contribute to the award total' in ' '.join(text.split())
 if exclusion and not pg:
  for m in modules:
   peers=[x for x in modules if (x['stage'],x['semester'])==(m['stage'],m['semester'])]
   if m['semester']==3 and len(peers)==1 and m['type']=='elective' and m['credits']==120:m['additional']=True
 known=all(m['credits'] is not None for m in modules)
 if not known:warnings.append('Individual module/group credits are not included in this export. They have not been inferred.')
 if pg:warnings.append('This export does not identify the full-time/part-time allocation of each schedule row. Intake sequences are confirmed from the narrative; the module lists are a combined source schedule, not a verified route timetable.')
 if any(m['type']=='elective' for m in modules):warnings.append('Elective groups are shown as slots. Their individual choices are not included in this course PDF.')
 if 'CM1112' in text and any(m['code']=='CE1337' for m in modules):warnings.append('The delivery table lists CE1337 Programming Bootcamp; a narrative note still refers to CM1112 Introduction to Programming. The diagram follows the table.')
 if known and not pg:
  total=sum(m['credits'] for m in modules if not m['additional'])
  if total!=int(credit[1]):raise ValueError(f'Listed award credits ({total}) do not match declared award credits ({credit[1]}). Review delivery variants or optional modules before publishing.')
 routes=intake_routes(text) if pg else {}
 if pg and not routes:warnings.append('No intake sequences were recognised. Only the published semester schedule is shown.')
 return {'id':code,'title':title,'level':'PG' if pg else 'UG','awardCredits':int(credit[1]),'sourceDate':date.strip(),'sourceFile':filename,'modules':modules,'routes':routes,'warnings':warnings,'duplicatesCollapsed':duplicates,'allocationVerified':not pg,'creditTotalChecked':known and not pg}

def group_key(code):
 return ' '.join(code.upper().split())

def parse_group(text, filename):
 code=re.search(r'^\s*Group Code\s+(.+)$',text,re.M)
 title=re.search(r'^\s*Group Title\s+(.+)$',text,re.M)
 if not code or not title:raise ValueError('Group code or title not found')
 members=[];page=1
 for line in text.split('\n'):
  page+=line.count('\f')
  m=re.match(r'^\s*(\d+)\s+Semester\s+(\d+)\s+Elective\s+([A-Z]{2,4}\d{3,4})\s{2,}(.+?)\s{2,}(?:Yes|No)\s+\d+\.\d+\s+(\d+)\s*$',line)
  if m:
   stage,sem,c,name,credits=m.groups()
   members.append({'stage':int(stage),'semester':int(sem),'code':c,'title':name.strip(),'credits':int(credits),'page':page})
 if not members:raise ValueError('No elective module rows recognised')
 return {'code':code[1].strip(),'title':re.sub(r'\s+APPROVED$','',title[1].strip()),'rule':'Choose one from','members':members,'sourceFile':filename}

def build(source,out):
 pdfs=sorted(p for p in source.rglob('*') if p.suffix.lower()=='.pdf')
 if not pdfs:raise ValueError('No PDFs found in '+str(source))
 courses=[];groups={};errors=[]
 for p in pdfs:
  try:
   text=extract(p)
   if re.search(r'^\s*Group Code\s+',text,re.M):
    g=parse_group(text,p.name);key=group_key(g['code'])
    if key in groups:raise ValueError('Duplicate elective group: '+g['code'])
    g['_path']=p;groups[key]=g;continue
   c=parse(text,p.name);c['sha256']=hashlib.sha256(p.read_bytes()).hexdigest();c['_path']=p;courses.append(c)
  except Exception as e:errors.append(f'{p.name}: {e}')
 if not courses:errors.append('No course PDFs found')
 for c in courses:
  unresolved=[]
  for m in c['modules']:
   if m['type']!='elective':continue
   g=groups.get(group_key(m['code']))
   if not g:unresolved.append(m['code']);continue
   members=[x for x in g['members'] if x['stage']==m['stage'] and x['semester']==m['semester']]
   if not members:
    errors.append(f"{c['id']}: {m['code']} has no choices for this stage/semester");continue
   if m['credits'] is not None and any(x['credits']!=m['credits'] for x in members):
    errors.append(f"{c['id']}: {m['code']} choice credits differ from the course slot");continue
   m['choices']=members;m['selectionRule']='Choose one from'
   m['groupSource']='pdfs/group-'+re.sub(r'[^a-z0-9]+','-',group_key(g['code']).lower()).strip('-')+'.pdf'
  c['warnings']=[w for w in c['warnings'] if not w.startswith('Elective groups are shown')]
  if unresolved:c['warnings'].append('Group PDFs not yet supplied for: '+', '.join(sorted(set(unresolved)))+'. These remain unexpanded slots.')
 ids=[c['id'] for c in courses]
 if len(ids)!=len(set(ids)):errors.append('More than one PDF has the same course code. Replace the old PDF instead of retaining two versions.')
 report={'courses':[{'id':c['id'],'title':c['title'],'warnings':c['warnings']} for c in courses],'errors':errors}
 ROOT.joinpath('validation-report.json').write_text(json.dumps(report,indent=2))
 if errors:raise ValueError('\n'.join(errors))
 if out.exists():shutil.rmtree(out)
 shutil.copytree(ROOT/'web',out);(out/'pdfs').mkdir()
 for g in groups.values():
  dest='group-'+re.sub(r'[^a-z0-9]+','-',group_key(g['code']).lower()).strip('-')+'.pdf'
  shutil.copy2(g['_path'],out/'pdfs'/dest)
 for c in courses:
  sourcepath=c.pop('_path'); dest=c['id']+'.pdf';shutil.copy2(sourcepath,out/'pdfs'/dest);c['sourceFile']='pdfs/'+dest
 data={'builtAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'courses':courses}
 (out/'gallery-data.js').write_text('window.COURSE_GALLERY='+json.dumps(data,ensure_ascii=True).replace('</','<\\/')+';\n')
 (out/'.nojekyll').write_text('')
 print(f'Built {len(courses)} courses; {sum(len(c["modules"]) for c in courses)} scheduled entries.')
 for c in courses:print(f'{c["id"]}: {c["title"]}; '+('credit total checked' if c['creditTotalChecked'] else 'source limitations flagged'))
 return data

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,default=ROOT/'course-pdfs');ap.add_argument('--output',type=Path,default=ROOT/'dist');args=ap.parse_args()
 try:build(args.source,args.output)
 except Exception as e:print('BUILD BLOCKED: '+str(e),file=sys.stderr);sys.exit(1)
