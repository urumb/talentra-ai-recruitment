import os, uuid, hashlib, re, json
from urllib.request import Request,urlopen
from pathlib import Path
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor,as_completed
from typing import Literal
import fitz,jwt
from docx import Document
from fastapi import FastAPI,HTTPException,Depends,Header,UploadFile,File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field,field_validator
from sqlalchemy import create_engine,String,Float,Integer,DateTime,ForeignKey,JSON,Text
from sqlalchemy.orm import DeclarativeBase,Mapped,mapped_column,sessionmaker,Session
URL=os.getenv('DATABASE_URL','sqlite:///./talentra.db'); engine=create_engine(URL,connect_args={'check_same_thread':False} if URL.startswith('sqlite') else {}); SessionLocal=sessionmaker(bind=engine); SECRET=os.getenv('JWT_SECRET','development-only-change-me'); UPLOADS=Path(os.getenv('UPLOAD_DIR','./uploads')); UPLOADS.mkdir(exist_ok=True)
class Base(DeclarativeBase):pass
class User(Base): __tablename__='users';id:Mapped[str]=mapped_column(String,primary_key=True);email:Mapped[str]=mapped_column(String,unique=True);role:Mapped[str]=mapped_column(String);org:Mapped[str]=mapped_column(String)
class Requisition(Base): __tablename__='requisitions';id:Mapped[str]=mapped_column(String,primary_key=True);title:Mapped[str]=mapped_column(String);client:Mapped[str]=mapped_column(String);location:Mapped[str]=mapped_column(String);description:Mapped[str]=mapped_column(Text);scorecard:Mapped[dict]=mapped_column(JSON);created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Candidate(Base):
 __tablename__='candidates';id:Mapped[str]=mapped_column(String,primary_key=True);requisition_id:Mapped[str]=mapped_column(ForeignKey('requisitions.id'));name:Mapped[str]=mapped_column(String);email:Mapped[str]=mapped_column(String,unique=True);phone:Mapped[str]=mapped_column(String);role:Mapped[str]=mapped_column(String);experience:Mapped[float]=mapped_column(Float);skills:Mapped[list]=mapped_column(JSON);notice_days:Mapped[int]=mapped_column(Integer);raw_text:Mapped[str]=mapped_column(Text);score:Mapped[float]=mapped_column(Float);confidence:Mapped[str]=mapped_column(String);stage:Mapped[str]=mapped_column(String);evidence:Mapped[dict]=mapped_column(JSON);consent:Mapped[str]=mapped_column(String,default='Pending');deleted_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
class Batch(Base): __tablename__='batches';id:Mapped[str]=mapped_column(String,primary_key=True);requisition_id:Mapped[str]=mapped_column(ForeignKey('requisitions.id'));created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Resume(Base): __tablename__='resumes';id:Mapped[str]=mapped_column(String,primary_key=True);batch_id:Mapped[str]=mapped_column(ForeignKey('batches.id'));candidate_id:Mapped[str|None]=mapped_column(ForeignKey('candidates.id'),nullable=True);filename:Mapped[str]=mapped_column(String);path:Mapped[str]=mapped_column(String);sha256:Mapped[str]=mapped_column(String);status:Mapped[str]=mapped_column(String);error:Mapped[str|None]=mapped_column(Text,nullable=True)
class Submission(Base): __tablename__='submissions';id:Mapped[str]=mapped_column(String,primary_key=True);candidate_id:Mapped[str]=mapped_column(ForeignKey('candidates.id'));client_org:Mapped[str]=mapped_column(String)
class Audit(Base): __tablename__='audits';id:Mapped[str]=mapped_column(String,primary_key=True);actor_id:Mapped[str]=mapped_column(String);action:Mapped[str]=mapped_column(String);target:Mapped[str]=mapped_column(String);created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
Base.metadata.create_all(engine)
def db():
 d=SessionLocal()
 try:yield d
 finally:d.close()
def me(a:str|None=Header(default=None),d:Session=Depends(db)):
 if not a or not a.startswith('Bearer '):raise HTTPException(401,'Authentication required')
 try:u=d.get(User,jwt.decode(a[7:],SECRET,algorithms=['HS256'])['sub'])
 except jwt.PyJWTError:raise HTTPException(401,'Invalid session')
 if not u:raise HTTPException(401,'Unknown user')
 return u
def rec(u=Depends(me)):
 if u.role!='RECRUITER':raise HTTPException(403,'Recruiter access required')
 return u
def audit(d,u,action,target):d.add(Audit(id=str(uuid.uuid4()),actor_id=u.id,action=action,target=target))
def score(c,card):
 text=c.get('raw_text','');skills={str(x).lower() for x in c.get('skills',[])};total=0;ev={}
 for r in card.get('criteria',[]):
  typ,w,label=r['type'],r['weight'],r['label'];ratio=0;q=None;status='unknown'
  if typ in ('skills','location','education'):
   vals=[x.lower() for x in r.get('values',[])];found=[x for x in vals if x in skills or re.search(r'\b'+re.escape(x)+r'\b',text,re.I)];ratio=len(found)/len(vals) if vals else 0;status='matched' if found else 'missing';q=found[0] if found else None;ev[label]={'status':status,'matched':found,'quote':q,'source_document':c.get('source_document'),'page':1 if q else None,'confidence':c.get('confidence','unknown')}
  elif typ=='experience':
   got=float(c.get('experience',0));minimum=float(r.get('min') or 0);ratio=min(got/minimum,1) if minimum else 0;status='matched' if ratio==1 else ('unknown' if got else 'missing');q=f'{got:g} years experience' if got else None;ev[label]={'status':status,'quote':q,'source_document':c.get('source_document'),'page':1 if q else None,'confidence':c.get('confidence','unknown')}
  elif typ=='notice':
   days=c.get('notice_days');ratio=1 if days is not None and days<=r.get('max',-1) else 0;status='matched' if ratio else ('unknown' if days is None else 'missing');q=f'Notice period: {days} days' if days is not None else None;ev[label]={'status':status,'quote':q,'source_document':c.get('source_document'),'page':1 if q else None,'confidence':c.get('confidence','unknown')}
  total+=w*ratio
 return round(total,1),ev
class Login(BaseModel):email:str;password:str
class Criterion(BaseModel):label:str;type:Literal['skills','experience','notice','location','education'];weight:float;values:list[str]=[];min:float|None=None;max:int|None=None
class Card(BaseModel):
 criteria:list[Criterion]
 @field_validator('criteria')
 @classmethod
 def valid(cls,v):
  if not v or abs(sum(x.weight for x in v)-100)>.01:raise ValueError('Scorecard weights must total 100')
  return v
class ReqIn(BaseModel):title:str;client:str;location:str='';description:str;scorecard:Card
class JD(BaseModel):description:str=Field(min_length=20)
class Stage(BaseModel):stage:str
class Consent(BaseModel):status:Literal['Granted','Withdrawn','Pending']
def profile(text):
 email=re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',text);phone=re.search(r'(?:\+?91[- ]?)?[6-9]\d{9}',text);yrs=re.search(r'(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)',text,re.I);notice=re.search(r'(\d+)\s*days?\s*notice',text,re.I);known=[x for x in ['Python','Java','Spring Boot','Microservices','React','AWS','Kafka','SQL','Node.js'] if re.search(r'\b'+re.escape(x)+r'\b',text,re.I)];lines=[x.strip() for x in text.splitlines() if x.strip()];return {'name':lines[0][:100] if lines else 'Unknown candidate','email':email.group(0).lower() if email else '','phone':re.sub(r'\D','',phone.group(0))[-10:] if phone else '','experience':float(yrs.group(1)) if yrs else 0,'notice_days':int(notice.group(1)) if notice else None,'skills':known}
def parse(path):
 if path.suffix.lower()=='.docx':return '\n'.join(p.text for p in Document(path).paragraphs)
 if path.suffix.lower()!='.pdf':raise ValueError('Only PDF and DOCX files are supported')
 pdf=fitz.open(path);text='\n'.join(p.get_text() for p in pdf)
 if len(text.strip())<30:
  try:
   import pytesseract
   from PIL import Image
   pages=[]
   for page in pdf:
    pix=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False);pages.append(pytesseract.image_to_string(Image.frombytes('RGB',(pix.width,pix.height),pix.samples)))
   text='\n'.join(pages)
  except Exception as e:raise ValueError('Scanned PDF OCR failed; install Tesseract and verify it is on PATH: '+str(e))
 return text
def process(rid):
 d=SessionLocal();r=d.get(Resume,rid)
 try:
  r.status='processing';d.commit();text=parse(Path(r.path));p=profile(text);b=d.get(Batch,r.batch_id);req=d.get(Requisition,b.requisition_id);old=(d.query(Candidate).filter_by(email=p['email']).first() if p['email'] else None) or (d.query(Candidate).filter_by(phone=p['phone']).first() if p['phone'] else None)
  if old:r.status='duplicate';r.error='Possible duplicate: '+old.id;d.commit();return
  if not p['email']:raise ValueError('Missing email; candidate requires manual completion')
  p.update(raw_text=text,source_document=r.filename,confidence='Medium');s,e=score(p,req.scorecard);c=Candidate(id=str(uuid.uuid4()),requisition_id=req.id,name=p['name'],email=p['email'],phone=p['phone'],role='Candidate',experience=p['experience'],skills=p['skills'],notice_days=p['notice_days'] or 0,raw_text=text,score=s,confidence='Medium',stage='Screened',evidence=e,consent='Pending');d.add(c);r.candidate_id=c.id;r.status='completed';d.commit()
 except Exception as e:r.status='failed';r.error=str(e);d.commit()
 finally:d.close()
app=FastAPI(title='Talentra API',version='0.2.0');app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:3000'],allow_methods=['*'],allow_headers=['*'])
@app.post('/api/auth/login')
def login(v:Login,d:Session=Depends(db)):
 u=d.query(User).filter_by(email=v.email).first()
 if not u or v.password!='DemoPass123!':raise HTTPException(401,'Invalid email or password')
 return {'access_token':jwt.encode({'sub':u.id,'exp':datetime.now(timezone.utc)+timedelta(hours=8)},SECRET,algorithm='HS256'),'role':u.role,'email':u.email}
@app.post('/api/jd/extract')
def jd(v:JD,u=Depends(rec)):
 if not os.getenv('LLM_API_KEY') or not os.getenv('LLM_MODEL'):raise HTTPException(503,'AI is not configured. Add LLM_API_KEY and LLM_MODEL, or create the scorecard manually.')
 payload={'model':os.environ['LLM_MODEL'],'response_format':{'type':'json_object'},'messages':[{'role':'system','content':'Extract only stated job requirements. Return JSON {"criteria":[{label,type,weight,values,min,max}]}. Allowed type: skills, experience, notice, location, education. Weights must total 100.'},{'role':'user','content':v.description}]}
 try:
  request=Request(os.getenv('LLM_BASE_URL','https://api.openai.com/v1/chat/completions'),data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+os.environ['LLM_API_KEY'],'Content-Type':'application/json'});response=json.loads(urlopen(request,timeout=45).read());result=json.loads(response['choices'][0]['message']['content']);Card.model_validate(result);return result
 except Exception as e:raise HTTPException(502,'AI extraction failed: '+str(e))
@app.post('/api/requisitions')
def create(v:ReqIn,u=Depends(rec),d:Session=Depends(db)):x=Requisition(id=str(uuid.uuid4()),title=v.title,client=v.client,location=v.location,description=v.description,scorecard=v.scorecard.model_dump());d.add(x);d.commit();return {'id':x.id}
@app.get('/api/requisitions')
def reqs(u=Depends(rec),d:Session=Depends(db)):return [{'id':x.id,'title':x.title,'client':x.client,'location':x.location,'scorecard':x.scorecard} for x in d.query(Requisition)]
@app.post('/api/requisitions/{req}/uploads')
async def upload(req:str,files:list[UploadFile]=File(...),u=Depends(rec),d:Session=Depends(db)):
 if not d.get(Requisition,req):raise HTTPException(404,'Requisition not found')
 if not files or len(files)>500:raise HTTPException(422,'Upload 1–500 files')
 b=Batch(id=str(uuid.uuid4()),requisition_id=req);d.add(b);rows=[]
 for f in files:
  ext=Path(f.filename or '').suffix.lower()
  if ext not in ('.pdf','.docx'):continue
  blob=await f.read();dest=UPLOADS/(str(uuid.uuid4())+ext);dest.write_bytes(blob);rows.append(Resume(id=str(uuid.uuid4()),batch_id=b.id,candidate_id=None,filename=f.filename or 'resume'+ext,path=str(dest),sha256=hashlib.sha256(blob).hexdigest(),status='queued',error=None))
 if not rows:raise HTTPException(422,'No PDF or DOCX files supplied')
 d.add_all(rows);audit(d,u,'upload',b.id);d.commit()
 with ThreadPoolExecutor(max_workers=min(4,len(rows))) as ex:
  for _ in as_completed([ex.submit(process,x.id) for x in rows]):pass
 return {'batch_id':b.id,'accepted':len(rows)}
@app.get('/api/batches/{bid}')
def batch(bid:str,u=Depends(rec),d:Session=Depends(db)):
 rows=d.query(Resume).filter_by(batch_id=bid).all();return {'total':len(rows),'counts':{s:sum(x.status==s for x in rows) for s in ['queued','processing','completed','failed','duplicate']},'files':[{'id':x.id,'filename':x.filename,'status':x.status,'error':x.error} for x in rows]}
@app.post('/api/resumes/{rid}/retry')
def retry(rid:str,u=Depends(rec),d:Session=Depends(db)):
 r=d.get(Resume,rid)
 if not r or r.status!='failed':raise HTTPException(404,'Retryable document not found')
 r.status='queued';r.error=None;d.commit();process(rid);return {'status':'completed'}
@app.get('/api/documents/{rid}')
def document(rid:str,u=Depends(rec),d:Session=Depends(db)):
 r=d.get(Resume,rid)
 if not r or not Path(r.path).exists():raise HTTPException(404,'Document not found')
 audit(d,u,'document_preview',rid);d.commit();return FileResponse(r.path,filename=r.filename)
@app.get('/api/candidates')
def candidates(requisition_id:str|None=None,u=Depends(rec),d:Session=Depends(db)):
 x=d.query(Candidate).filter(Candidate.deleted_at.is_(None)).all();return [{'id':z.id,'name':z.name,'role':z.role,'experience':z.experience,'skills':z.skills,'notice_days':z.notice_days,'score':z.score,'stage':z.stage,'confidence':z.confidence,'consent':z.consent} for z in sorted([z for z in x if not requisition_id or z.requisition_id==requisition_id],key=lambda z:z.score,reverse=True)]
@app.get('/api/candidates/{cid}')
def candidate(cid:str,u=Depends(rec),d:Session=Depends(db)):
 x=d.get(Candidate,cid)
 if not x or x.deleted_at:raise HTTPException(404,'Candidate not found')
 audit(d,u,'candidate_view',cid);d.commit();return {k:getattr(x,k) for k in ['id','name','email','phone','role','experience','skills','notice_days','score','stage','evidence','consent','raw_text']}
@app.patch('/api/candidates/{cid}/stage')
def stage(cid:str,v:Stage,u=Depends(rec),d:Session=Depends(db)):x=d.get(Candidate,cid);x.stage=v.stage;audit(d,u,'stage_change',cid);d.commit();return {'stage':x.stage}
@app.put('/api/candidates/{cid}/consent')
def consent(cid:str,v:Consent,u=Depends(rec),d:Session=Depends(db)):x=d.get(Candidate,cid);x.consent=v.status;audit(d,u,'consent',cid);d.commit();return {'consent':x.consent}
@app.post('/api/candidates/{cid}/deletion-request')
def delrequest(cid:str,u=Depends(rec),d:Session=Depends(db)):audit(d,u,'deletion_request',cid);d.commit();return {'status':'requested'}
@app.delete('/api/candidates/{cid}')
def delete(cid:str,u=Depends(rec),d:Session=Depends(db)):
 x=d.get(Candidate,cid);x.raw_text='';x.email='deleted-'+cid+'@invalid';x.phone='';x.deleted_at=datetime.utcnow();audit(d,u,'secure_delete',cid);d.commit();return {'status':'deleted'}
@app.get('/api/duplicates')
def duplicates(u=Depends(rec),d:Session=Depends(db)):return [{'resume_id':x.id,'filename':x.filename,'detail':x.error} for x in d.query(Resume).filter_by(status='duplicate')]
@app.post('/api/candidates/{cid}/submit')
def submit(cid:str,u=Depends(rec),d:Session=Depends(db)):
 c=d.get(Candidate,cid);req=d.get(Requisition,c.requisition_id);d.add(Submission(id=str(uuid.uuid4()),candidate_id=cid,client_org=req.client));c.stage='Submitted to Client';audit(d,u,'client_submit',cid);d.commit();return {'status':'submitted'}
@app.get('/api/client/submissions')
def client(u=Depends(me),d:Session=Depends(db)):
 if u.role!='CLIENT':raise HTTPException(403,'Client access required')
 ids=[x.candidate_id for x in d.query(Submission).filter_by(client_org=u.org)];return [{'id':x.id,'name':x.name.split()[0]+' •••','role':x.role,'experience':x.experience,'skills':x.skills,'score':x.score,'stage':x.stage,'evidence':x.evidence} for x in d.query(Candidate).filter(Candidate.id.in_(ids),Candidate.deleted_at.is_(None))]
@app.get('/api/audit')
def audits(u=Depends(rec),d:Session=Depends(db)):return [{'action':x.action,'target':x.target,'at':x.created_at.isoformat()} for x in d.query(Audit).order_by(Audit.created_at.desc()).limit(100)]
@app.get('/api/fairness')
def fairness(u=Depends(rec),d:Session=Depends(db)):
 x=d.query(Candidate).filter(Candidate.deleted_at.is_(None)).all();s=[z for z in x if z.stage in ('Shortlisted','Interview','Offered','Joined')];return {'sample_size':len(x),'recruiter_selected':len(s),'average_ai_score':round(sum(z.score for z in x)/len(x),1) if x else 0,'selected_average_ai_score':round(sum(z.score for z in s)/len(s),1) if s else 0,'note':'Monitoring only, not proof of unbiased AI. Protected attributes are excluded from scoring.'}
@app.get('/api/dashboard')
def dashboard(u=Depends(rec),d:Session=Depends(db)):x=d.query(Candidate).filter(Candidate.deleted_at.is_(None)).all();return {'active_requisitions':d.query(Requisition).count(),'candidates_processed':len(x),'awaiting_review':sum(z.stage=='Screened' for z in x),'shortlisted':sum(z.stage=='Shortlisted' for z in x)}
def seed():
 d=SessionLocal()
 if d.query(User).first():d.close();return
 d.add_all([User(id='u-rec',email='recruiter@talentra.demo',role='RECRUITER',org='Talentra'),User(id='u-client',email='client@acme.demo',role='CLIENT',org='Acme Systems')]);card={'criteria':[{'label':'Required skills','type':'skills','values':['Java','Spring Boot','Microservices'],'weight':55},{'label':'Experience','type':'experience','min':5,'weight':30},{'label':'Notice','type':'notice','max':60,'weight':15}]};r=Requisition(id='req-java',title='Senior Java Developer',client='Acme Systems',location='Noida',description='Demo',scorecard=card);d.add(r)
 for i,n,e,exp,skills,notice in [('CND-1','Ritika Bansal','ritika@example.demo',6.5,['Java','Spring Boot','Microservices'],60),('CND-2','Dev Mehta','dev@example.demo',7,['Java','Spring Boot','Microservices','AWS'],30)]:
  p={'skills':skills,'experience':exp,'notice_days':notice,'raw_text':f'{exp} years experience. Skills: {", ".join(skills)}. Notice period: {notice} days.','source_document':'demo.pdf','confidence':'High'};sc,ev=score(p,card);d.add(Candidate(id=i,requisition_id=r.id,name=n,email=e,phone='',role='Java Developer',experience=exp,skills=skills,notice_days=notice,raw_text=p['raw_text'],score=sc,confidence='High',stage='Submitted to Client' if i=='CND-2' else 'Screened',evidence=ev,consent='Granted'))
 d.add(Submission(id=str(uuid.uuid4()),candidate_id='CND-2',client_org='Acme Systems'));d.commit();d.close()
seed()
