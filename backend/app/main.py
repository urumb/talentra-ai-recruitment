import os, uuid, hashlib
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Float, Integer, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session
import jwt

URL=os.getenv("DATABASE_URL","sqlite:///./talentra.db")
engine=create_engine(URL, connect_args={"check_same_thread":False} if URL.startswith("sqlite") else {})
SessionLocal=sessionmaker(bind=engine)
SECRET=os.getenv("JWT_SECRET","development-only-change-me")
class Base(DeclarativeBase): pass
class User(Base):
    __tablename__="users"; id:Mapped[str]=mapped_column(String,primary_key=True); email:Mapped[str]=mapped_column(String,unique=True); role:Mapped[str]=mapped_column(String); org:Mapped[str]=mapped_column(String)
class Requisition(Base):
    __tablename__="requisitions"; id:Mapped[str]=mapped_column(String,primary_key=True); title:Mapped[str]=mapped_column(String); client:Mapped[str]=mapped_column(String); location:Mapped[str]=mapped_column(String); description:Mapped[str]=mapped_column(Text); scorecard:Mapped[dict]=mapped_column(JSON); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class Candidate(Base):
    __tablename__="candidates"; id:Mapped[str]=mapped_column(String,primary_key=True); requisition_id:Mapped[str]=mapped_column(ForeignKey("requisitions.id"),index=True); name:Mapped[str]=mapped_column(String); email:Mapped[str]=mapped_column(String,unique=True); phone:Mapped[str]=mapped_column(String); role:Mapped[str]=mapped_column(String); experience:Mapped[float]=mapped_column(Float); skills:Mapped[list]=mapped_column(JSON); notice_days:Mapped[int]=mapped_column(Integer); raw_text:Mapped[str]=mapped_column(Text); score:Mapped[float]=mapped_column(Float); confidence:Mapped[str]=mapped_column(String); stage:Mapped[str]=mapped_column(String,default="Screened"); evidence:Mapped[dict]=mapped_column(JSON); consent:Mapped[str]=mapped_column(String,default="Granted")
Base.metadata.create_all(engine)

def db():
    d=SessionLocal()
    try: yield d
    finally: d.close()
def current(authorization:str|None=Header(default=None), d:Session=Depends(db)):
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(401,"Authentication required")
    try: data=jwt.decode(authorization[7:],SECRET,algorithms=["HS256"])
    except jwt.PyJWTError: raise HTTPException(401,"Invalid session")
    u=d.get(User,data["sub"])
    if not u: raise HTTPException(401,"Unknown user")
    return u
def recruiter(u=Depends(current)):
    if u.role!="RECRUITER": raise HTTPException(403,"Recruiter access required")
    return u
def score(candidate, card):
    # Protected attributes deliberately never enter this function.
    skills={x.lower() for x in candidate["skills"]}; total=0; ev={}
    for rule in card["criteria"]:
        label=rule["label"]; w=rule["weight"]; val=0; found=[]
        if rule["type"]=="skills":
            required=[x.lower() for x in rule["values"]]; found=[x for x in required if x in skills]; val=len(found)/len(required) if required else 0
            ev[label]={"status":"matched" if found else "not_found","matched":found,"quote":candidate["raw_text"][:180] if found else None,"page":1}
        elif rule["type"]=="experience":
            val=min(candidate["experience"]/rule["min"],1); ev[label]={"status":"matched" if val==1 else "partial","quote":f"{candidate['experience']} years experience", "page":1}
        elif rule["type"]=="notice":
            val=1 if candidate["notice_days"]<=rule["max"] else 0; ev[label]={"status":"matched" if val else "not_found","quote":f"Notice period: {candidate['notice_days']} days", "page":1}
        total+=w*val
    return round(total,1),ev
def seed():
    d=SessionLocal()
    if d.query(User).first(): d.close(); return
    d.add_all([User(id="u-rec",email="recruiter@talentra.demo",role="RECRUITER",org="Talentra"),User(id="u-client",email="client@acme.demo",role="CLIENT",org="Acme Systems")])
    card={"criteria":[{"label":"Required technical skills","type":"skills","values":["Java","Spring Boot","Microservices"],"weight":45},{"label":"Relevant experience","type":"experience","min":5,"weight":25},{"label":"Notice period","type":"notice","max":60,"weight":10},{"label":"Location","type":"skills","values":["Noida"],"weight":5},{"label":"Preferred skills","type":"skills","values":["Kafka","AWS"],"weight":15}]}
    r=Requisition(id="req-java",title="Senior Java Developer",client="Acme Systems",location="Noida",description="Synthetic demo JD: Java, Spring Boot and Microservices. 5–8 years. Noida. Maximum 60 day notice.",scorecard=card); d.add(r)
    rows=[("CND-91022","Ritika Bansal","ritika@example.demo","Senior Java Developer",6.5,["Java","Spring Boot","Microservices","Kafka","Noida"],60),("CND-91047","Arjun Rawat","arjun@example.demo","KYC Analyst",3,["KYC","AML Checks","Excel"],30),("CND-91088","Pooja Nair","pooja@example.demo","Java Developer",4,["Java","Hibernate","REST APIs"],90),("CND-91101","Dev Mehta","dev@example.demo","Backend Engineer",7,["Java","Spring Boot","Microservices","AWS","Noida"],30)]
    for ident,name,email,role,exp,skills,notice in rows:
        payload={"skills":skills,"experience":exp,"notice_days":notice,"raw_text":f"Synthetic demo CV. {role}. {exp} years experience. Skills: {', '.join(skills)}. Notice period: {notice} days."}; s,e=score(payload,card)
        d.add(Candidate(id=ident,requisition_id=r.id,name=name,email=email,phone="+91 98XXXXXX10",role=role,experience=exp,skills=skills,notice_days=notice,raw_text=payload["raw_text"],score=s,confidence="High" if len(skills)>2 else "Medium",evidence=e,stage="Submitted to Client" if ident=="CND-91101" else "Screened"))
    d.commit();d.close()
seed()
app=FastAPI(title="Talentra API",version="0.1.0")
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:3000"],allow_methods=["*"],allow_headers=["*"])
class Login(BaseModel): email:str; password:str
class ReqIn(BaseModel): title:str; client:str; location:str; description:str; scorecard:dict
class StageIn(BaseModel): stage:Literal["Sourced","Parsed","Screened","Recruiter Reviewed","Submitted to Client","Shortlisted","Interview","Offered","Joined","Rejected","Withdrawn","On Hold"]
@app.post("/api/auth/login")
def login(v:Login,d:Session=Depends(db)):
    u=d.query(User).filter_by(email=v.email).first()
    if not u or v.password!="DemoPass123!": raise HTTPException(401,"Invalid email or password")
    return {"access_token":jwt.encode({"sub":u.id,"exp":datetime.now(timezone.utc)+timedelta(hours=8)},SECRET,algorithm="HS256"),"role":u.role,"email":u.email}
@app.get("/api/dashboard")
def dashboard(u=Depends(recruiter),d:Session=Depends(db)):
    c=d.query(Candidate).all(); return {"active_requisitions":d.query(Requisition).count(),"candidates_processed":len(c),"awaiting_review":sum(x.stage=="Screened" for x in c),"shortlisted":sum(x.stage=="Shortlisted" for x in c),"pipeline":{s:sum(x.stage==s for x in c) for s in ["Sourced","Parsed","Screened","Recruiter Reviewed","Submitted to Client","Shortlisted","Interview"]}}
@app.get("/api/requisitions")
def requisitions(u=Depends(recruiter),d:Session=Depends(db)): return [{"id":x.id,"title":x.title,"client":x.client,"location":x.location,"scorecard":x.scorecard} for x in d.query(Requisition).all()]
@app.post("/api/requisitions")
def create_req(v:ReqIn,u=Depends(recruiter),d:Session=Depends(db)):
    weights=sum(x.get("weight",0) for x in v.scorecard.get("criteria",[]));
    if abs(weights-100)>0.01: raise HTTPException(422,"Scorecard weights must total 100")
    x=Requisition(id=str(uuid.uuid4()),**v.model_dump());d.add(x);d.commit();return {"id":x.id}
@app.get("/api/candidates")
def candidates(requisition_id:str|None=None,q:str="",min_score:float=0,u=Depends(recruiter),d:Session=Depends(db)):
    items=d.query(Candidate).filter(Candidate.score>=min_score).all(); items=[x for x in items if (not requisition_id or x.requisition_id==requisition_id) and q.lower() in (x.name+x.role+" "+" ".join(x.skills)).lower()]
    return [{"id":x.id,"name":x.name,"role":x.role,"experience":x.experience,"skills":x.skills,"notice_days":x.notice_days,"score":x.score,"stage":x.stage,"confidence":x.confidence} for x in sorted(items,key=lambda z:z.score,reverse=True)]
@app.get("/api/candidates/{candidate_id}")
def candidate(candidate_id:str,u=Depends(recruiter),d:Session=Depends(db)):
    x=d.get(Candidate,candidate_id)
    if not x: raise HTTPException(404,"Candidate not found")
    return {"id":x.id,"name":x.name,"email":x.email,"phone":x.phone,"role":x.role,"experience":x.experience,"skills":x.skills,"notice_days":x.notice_days,"score":x.score,"stage":x.stage,"evidence":x.evidence,"consent":x.consent,"raw_text":x.raw_text}
@app.patch("/api/candidates/{candidate_id}/stage")
def stage(candidate_id:str,v:StageIn,u=Depends(recruiter),d:Session=Depends(db)):
    x=d.get(Candidate,candidate_id)
    if not x: raise HTTPException(404,"Candidate not found")
    x.stage=v.stage;d.commit();return {"stage":x.stage}
@app.get("/api/client/submissions")
def client_list(u=Depends(current),d:Session=Depends(db)):
    if u.role!="CLIENT": raise HTTPException(403,"Client access required")
    return [{"id":x.id,"name":x.name.split()[0]+" •••","role":x.role,"experience":x.experience,"skills":x.skills,"score":x.score,"stage":x.stage,"evidence":x.evidence} for x in d.query(Candidate).filter(Candidate.stage.in_(["Submitted to Client","Shortlisted","Interview"])).all()]
