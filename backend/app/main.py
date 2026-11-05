"""Talentra API: requisitions, bulk CV processing, evidence-based scoring, client portal, privacy and monitoring."""
import os, uuid, hashlib, hmac, re, json, secrets, threading, logging, time
from collections import defaultdict
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from pathlib import Path
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
import fitz, jwt
from docx import Document
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import create_engine, String, Float, Integer, DateTime, ForeignKey, JSON, Text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session

log = logging.getLogger('talentra')


def load_dotenv(files=None):
    """Load KEY=VALUE lines from backend/.env or the repo-root .env for local runs. Real environment variables always win."""
    if os.getenv('TALENTRA_NO_DOTENV'): return
    for f in files or (Path(__file__).resolve().parents[1] / '.env', Path(__file__).resolve().parents[2] / '.env'):
        if not f.is_file(): continue
        for line in f.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line: continue
            k, v = line.split('=', 1); v = re.sub(r'\s+#.*$', '', v).strip().strip('"').strip("'")
            os.environ.setdefault(k.strip(), v)


load_dotenv()
URL = os.getenv('DATABASE_URL', 'sqlite:///./talentra.db')
engine = create_engine(URL, connect_args={'check_same_thread': False, 'timeout': 30} if URL.startswith('sqlite') else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
DEV_SECRET = 'development-only-change-me'
SECRET = os.getenv('JWT_SECRET', DEV_SECRET)
if os.getenv('APP_ENV', 'development') == 'production' and (SECRET == DEV_SECRET or len(SECRET) < 32):
    raise RuntimeError('Set JWT_SECRET to a random value of at least 32 characters when APP_ENV=production')
UPLOADS = Path(os.getenv('UPLOAD_DIR', './uploads')); UPLOADS.mkdir(parents=True, exist_ok=True)
MAX_BYTES = int(float(os.getenv('UPLOAD_MAX_MB', '10')) * 1024 * 1024)
WORKERS = max(1, int(os.getenv('PROCESS_WORKERS', '4')))
OCR_MAX_PAGES = 20

STAGES = ['Sourced', 'Screened', 'Submitted to Client', 'Shortlisted', 'Interview proposed', 'Interview scheduled', 'Offered', 'Joined', 'Rejected by Client', 'Rejected']
SELECTED_STAGES = {'Submitted to Client', 'Shortlisted', 'Interview proposed', 'Interview scheduled', 'Offered', 'Joined', 'Rejected by Client'}


def ref(cid):
    return cid.replace('-', '')[-6:].upper()


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    role: Mapped[str] = mapped_column(String)  # RECRUITER | CLIENT | DELIVERY_HEAD
    org: Mapped[str] = mapped_column(String)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)


class Requisition(Base):
    __tablename__ = 'requisitions'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    client: Mapped[str] = mapped_column(String)
    location: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    scorecard: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Candidate(Base):
    __tablename__ = 'candidates'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    requisition_id: Mapped[str] = mapped_column(ForeignKey('requisitions.id'))
    name: Mapped[str] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    phone: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    experience: Mapped[float | None] = mapped_column(Float, nullable=True)
    skills: Mapped[list] = mapped_column(JSON)
    notice_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_text: Mapped[str] = mapped_column(Text)  # pages separated by form feed (\f)
    score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String)
    stage: Mapped[str] = mapped_column(String)
    evidence: Mapped[dict] = mapped_column(JSON)
    consent: Mapped[str] = mapped_column(String, default='Pending')
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Batch(Base):
    __tablename__ = 'batches'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    requisition_id: Mapped[str] = mapped_column(ForeignKey('requisitions.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Resume(Base):
    __tablename__ = 'resumes'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey('batches.id'))
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey('candidates.id'), nullable=True)  # result candidate, or the matched candidate for duplicates
    filename: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)
    sha256: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)  # queued processing completed failed duplicate resolved_duplicate deleted
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Submission(Base):
    __tablename__ = 'submissions'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey('candidates.id'))
    client_org: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ClientReview(Base):
    __tablename__ = 'client_reviews'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey('candidates.id'))
    client_org: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    slots: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class DeletionRequest(Base):
    __tablename__ = 'deletion_requests'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey('candidates.id'))
    requested_by: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default='Requested')  # Requested | Completed | Declined
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Audit(Base):
    __tablename__ = 'audits'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    actor_id: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    target: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


Base.metadata.create_all(engine)


# ---------------------------------------------------------------- auth
def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    return 'pbkdf2$200000$%s$%s' % (salt, hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), 200000).hex())


def check_password(pw: str, stored: str | None) -> bool:
    try:
        _, rounds, salt, digest = (stored or '').split('$')
        return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256', pw.encode(), salt.encode(), int(rounds)).hex(), digest)
    except ValueError:
        return False


def db():
    d = SessionLocal()
    try:
        yield d
    finally:
        d.close()


def me(authorization: str | None = Header(default=None), d: Session = Depends(db)):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Authentication required')
    try:
        u = d.get(User, jwt.decode(authorization[7:], SECRET, algorithms=['HS256'])['sub'])
    except (jwt.PyJWTError, KeyError):
        raise HTTPException(401, 'Invalid or expired session')
    if not u:
        raise HTTPException(401, 'Unknown user')
    return u


def rec(u=Depends(me)):
    if u.role != 'RECRUITER':
        raise HTTPException(403, 'Recruiter access required')
    return u


def client_user(u=Depends(me)):
    if u.role != 'CLIENT':
        raise HTTPException(403, 'Client access required')
    return u


def monitor_user(u=Depends(me)):
    if u.role not in ('RECRUITER', 'DELIVERY_HEAD'):
        raise HTTPException(403, 'Recruiter or delivery-head access required')
    return u


def audit(d, u, action, target):
    d.add(Audit(id=str(uuid.uuid4()), actor_id=u.id, action=action, target=target))


# ---------------------------------------------------------------- extraction + scoring
SKILL_VOCAB = ['Python', 'Java', 'Spring Boot', 'Microservices', 'React', 'Angular', 'Vue', 'AWS', 'Azure', 'GCP', 'Kafka', 'SQL', 'PostgreSQL', 'MySQL', 'MongoDB', 'Node.js', 'TypeScript', 'JavaScript', 'Docker', 'Kubernetes', 'Django', 'FastAPI', 'Flask', 'C#', '.NET', 'Go', 'Redis', 'Terraform', 'Git', 'REST', 'GraphQL', 'Hibernate', 'Selenium', 'Jenkins']
EXP_RE = re.compile(r'(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)\b', re.I)


def term_re(t):
    return re.compile(r'(?<![\w])' + re.escape(t) + r'(?![\w])', re.I)


def snippet(text, m):
    """The CV line containing a regex match, trimmed, plus the 1-based page it appears on."""
    page = text.count('\f', 0, m.start()) + 1
    a = text.rfind('\n', 0, m.start()) + 1
    b = text.find('\n', m.end()); b = len(text) if b < 0 else b
    line = re.sub(r'\s+', ' ', text[a:b].replace('\f', ' ')).strip()
    if len(line) > 180:
        line = line[:180] + '…'
    return line, page


def find_experience(text):
    """Years of experience stated in the CV, only when phrased as experience. Returns (years, regex match) or (None, None)."""
    best = None
    for m in EXP_RE.finditer(text):
        ctx = text[max(0, m.start() - 40):m.end() + 40].lower()
        if 'experience' in ctx or 'exp' in ctx:
            v = float(m.group(1))
            if v <= 50 and (best is None or v > best[0]):
                best = (v, m)
    return best if best else (None, None)


CTC_RE = re.compile(r'\b(expected|current|present)?\s*ctc\b[^0-9\n]{0,25}?(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?|lacs?)', re.I)


def find_ctc(text):
    """CTC in lakh per annum, as stated in the CV. Prefers an *expected* CTC over a current one. Returns (lpa, match) or (None, None)."""
    ms = [m for m in CTC_RE.finditer(text) if float(m.group(2)) < 1000]
    pick = next((m for m in ms if (m.group(1) or '').lower() == 'expected'), ms[0] if ms else None)
    return (float(pick.group(2)), pick) if pick else (None, None)


def find_notice(text):
    if (m := re.search(r'notice(?:\s+period)?\s*(?:is|of|[:\-])?\s*(\d+)\s*(days?|months?)', text, re.I)) or (m := re.search(r'(\d+)\s*(days?|months?)\s*(?:of\s*)?notice', text, re.I)):
        n = int(m.group(1)); return (n * 30 if m.group(2).lower().startswith('month') else n), m
    if m := re.search(r'immediate(?:ly)?\s+(?:joiner|available|joining)', text, re.I):
        return 0, m
    return None, None


def profile(text, extra_terms=()):
    """Rule-based extraction. Anything not found stays None/empty (unknown), never guessed."""
    email = re.search(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}', text)
    phone = re.search(r'(?<!\d)(?:\+?91[- ]?)?[6-9]\d{9}(?!\d)', text)
    exp, _ = find_experience(text); notice, _ = find_notice(text)
    vocab = list(dict.fromkeys(list(SKILL_VOCAB) + [str(x) for x in extra_terms]))
    skills = [x for x in vocab if term_re(x).search(text)]
    first = next((x.strip() for x in text.replace('\f', '\n').splitlines() if x.strip()), '')
    name = first if re.fullmatch(r"[A-Za-z][A-Za-z.'\- ]{1,38}", first) and 1 < len(first.split()) <= 4 else 'Unnamed candidate'
    found = sum(bool(x) for x in (email, phone, exp is not None, skills))
    return {'name': name, 'email': email.group(0).lower() if email else None, 'phone': re.sub(r'\D', '', phone.group(0))[-10:] if phone else '', 'experience': exp, 'notice_days': notice, 'skills': skills,
            'confidence': 'High' if found == 4 else 'Medium' if found == 3 else 'Low'}


def score(c, card):
    """Deterministic score from the scorecard and CV text only. Name/age/gender/photo/marital status are never read.
    Every criterion carries a verbatim CV quote and page. Facts not stated in the CV are 'unknown' and earn 0 points (never a rejection)."""
    text = c.get('raw_text', '') or ''
    skills = {str(x).lower() for x in c.get('skills') or []}
    src = c.get('source_document'); paged = bool(src) and str(src).lower().endswith('.pdf'); conf = c.get('confidence', 'unknown')
    total = 0.0; ev = {}
    for r in card.get('criteria', []):
        typ, w, label = r['type'], float(r['weight']), r['label']
        while label in ev:
            label += ' ·'
        ratio = 0.0; status = 'unknown'; q = None; page = None; extra = {}
        if typ in ('skills', 'location', 'education'):
            vals = [x for x in r.get('values', []) if str(x).strip()]; found = []; quotes = []
            for v in vals:
                m = term_re(v).search(text)
                if m or v.lower() in skills:
                    found.append(v)
                if m:
                    ln, pg = snippet(text, m)
                    if ln not in quotes: quotes.append(ln)
                    page = page or pg
            if quotes:
                q = '  ·  '.join(quotes[:3])
            ratio = (len(found) / len(vals) if typ == 'skills' else 1.0) if found and vals else 0.0
            status = 'unknown' if not text.strip() else ('matched' if vals and len(found) == len(vals) or (typ != 'skills' and found) else 'partial' if found else 'not_found')
            extra = {'matched': found, 'expected': vals}
        elif typ == 'experience':
            got, m = find_experience(text)
            if got is None and c.get('experience') is not None: got = float(c['experience'])
            minimum = float(r.get('min') or 0)
            if got is not None:
                ratio = min(got / minimum, 1) if minimum else 1.0; status = 'matched' if ratio >= 1 else 'partial'
                q, page = snippet(text, m) if m else (f'{got:g} years experience', None)
            extra = {'expected_min_years': minimum, 'found_years': got}
        elif typ == 'ctc':
            val, m = find_ctc(text); mx = r.get('max')
            if val is not None:
                ratio = 1.0 if mx is None or val <= mx else 0.0; status = 'matched' if ratio else 'not_met'
                q, page = snippet(text, m)
            extra = {'expected_max_lpa': mx, 'found_lpa': val}
        elif typ == 'notice':
            days, m = find_notice(text)
            if days is None and c.get('notice_days') is not None: days = c['notice_days']
            mx = r.get('max')
            if days is not None:
                ratio = 1.0 if mx is None or days <= mx else 0.0; status = 'matched' if ratio else 'not_met'
                q, page = snippet(text, m) if m else (f'Notice period: {days} days', None)
            extra = {'expected_max_days': mx, 'found_days': days}
        if not paged: page = None
        points = round(w * ratio, 2); total += points
        ev[label] = {'status': status, 'quote': q, 'source_document': src, 'page': page, 'confidence': conf, 'weight': w, 'points': points, **extra}
    return round(total, 1), ev


def rescore(d, c, req):
    src = d.query(Resume).filter_by(candidate_id=c.id, status='completed').first()
    s, ev = score({'raw_text': c.raw_text, 'skills': c.skills, 'experience': c.experience, 'notice_days': c.notice_days, 'source_document': src.filename if src else None, 'confidence': c.confidence}, req.scorecard)
    c.score, c.evidence = s, ev


# ---------------------------------------------------------------- document parsing + background processing
def tesseract():
    """Import pytesseract and point it at the Windows default install if tesseract is not on PATH (or TESSERACT_CMD is set)."""
    import pytesseract
    cmd = os.getenv('TESSERACT_CMD') or next((x for x in (r'C:\Program Files\Tesseract-OCR\tesseract.exe', r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe') if Path(x).exists()), None)
    if cmd and hasattr(pytesseract, 'pytesseract'): pytesseract.pytesseract.tesseract_cmd = cmd
    return pytesseract


def ocr_page(page):
    pytesseract = tesseract()
    from PIL import Image
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    return pytesseract.image_to_string(Image.frombytes('RGB', (pix.width, pix.height), pix.samples))


def parse(path):
    """Returns a list of page texts (a DOCX is a single 'page')."""
    ext = path.suffix.lower()
    if ext == '.docx':
        try:
            doc = Document(path)
        except Exception:
            raise ValueError('The file is corrupt or is not a readable DOCX')
        parts = [p.text for p in doc.paragraphs] + [c.text for t in doc.tables for row in t.rows for c in row.cells]
        return ['\n'.join(parts)]
    if ext != '.pdf':
        raise ValueError('Only PDF and DOCX files are supported')
    try:
        pdf = fitz.open(path)
    except Exception:
        raise ValueError('The file is corrupt or is not a readable PDF')
    if pdf.needs_pass:
        raise ValueError('PDF is password protected')
    pages = [p.get_text() for p in pdf]
    if sum(len(p.strip()) for p in pages) < 30:  # scanned / image-only: OCR
        try:
            tesseract().get_tesseract_version()
        except Exception as e:
            raise ValueError('Scanned PDF needs OCR, but Tesseract is not available on the server: ' + str(e)[:150])
        if len(pdf) > OCR_MAX_PAGES:
            raise ValueError(f'Scanned PDF has more than {OCR_MAX_PAGES} pages; OCR limit exceeded')
        try:
            pages = [ocr_page(p) for p in pdf]
        except Exception as e:
            raise ValueError('OCR failed: ' + str(e)[:200])
    return pages


CREATE_LOCK = threading.Lock()
POOL = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix='cv')


def enqueue(rid, force=False):
    POOL.submit(process, rid, force)


def find_duplicate(d, r, p):
    q = d.query(Candidate).filter(Candidate.deleted_at.is_(None))
    if p['email'] and (c := q.filter_by(email=p['email']).first()): return c, 'email'
    if p['phone'] and (c := q.filter_by(phone=p['phone']).first()): return c, 'phone'
    same = d.query(Resume).filter(Resume.sha256 == r.sha256, Resume.id != r.id, Resume.status == 'completed', Resume.candidate_id.isnot(None)).first()
    if same and (c := d.get(Candidate, same.candidate_id)) and not c.deleted_at: return c, 'identical file'
    return None, None


def process(rid, force=False, cid=None):
    """Process one document. Every failure is contained to this document."""
    d = SessionLocal(); r = None
    try:
        r = d.get(Resume, rid)
        if not r or r.status not in ('queued', 'processing'):
            return
        r.status = 'processing'; r.error = None; d.commit()
        pages = parse(Path(r.path)); text = '\f'.join(pages)
        if len(text.strip()) < 30:
            raise ValueError('No readable text found in the document')
        req = d.get(Requisition, d.get(Batch, r.batch_id).requisition_id)
        extra = [v for c in req.scorecard.get('criteria', []) if c['type'] == 'skills' for v in c.get('values', [])]
        p = profile(text, extra)
        with CREATE_LOCK:
            dup, why = (None, None) if force else find_duplicate(d, r, p)
            if dup:
                r.status = 'duplicate'; r.candidate_id = dup.id; r.error = f'Matches an existing candidate ({why})'; d.commit(); return
            if force and p['email'] and d.query(Candidate).filter_by(email=p['email']).first():
                raise ValueError('A candidate with this email already exists; discard this document instead')
            sc, ev = score({**p, 'raw_text': text, 'source_document': r.filename}, req.scorecard)
            c = Candidate(id=cid or str(uuid.uuid4()), requisition_id=req.id, name=p['name'], email=p['email'], phone=p['phone'], role=req.title, experience=p['experience'], skills=p['skills'], notice_days=p['notice_days'], raw_text=text, score=sc, confidence=p['confidence'], stage='Sourced', evidence=ev, consent='Pending')
            d.add(c); r.candidate_id = c.id; r.status = 'completed'; d.commit()
    except IntegrityError:
        d.rollback(); r = d.get(Resume, rid); r.status = 'duplicate'; r.error = 'Matches an existing candidate (email)'; d.commit()
    except Exception as e:
        d.rollback()
        try:
            r = d.get(Resume, rid); r.status = 'failed'; r.error = (str(e).replace(r.path, r.filename) if r.path else str(e) or e.__class__.__name__)[:400] or 'Processing failed'; d.commit()
        except Exception:
            log.exception('could not record failure for %s', rid)
    finally:
        d.close()


def recover_pending():
    """Re-queue documents interrupted by a restart."""
    d = SessionLocal()
    try:
        ids = [x.id for x in d.query(Resume).filter(Resume.status.in_(['queued', 'processing']))]
    finally:
        d.close()
    for i in ids: enqueue(i)


# ---------------------------------------------------------------- schemas
class Login(BaseModel):
    email: str
    password: str


class Criterion(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    type: Literal['skills', 'experience', 'notice', 'ctc', 'location', 'education']
    weight: float = Field(ge=0, le=100)
    values: list[str] = []
    min: float | None = None
    max: float | None = None


class Card(BaseModel):
    criteria: list[Criterion]

    @field_validator('criteria')
    @classmethod
    def valid(cls, v):
        if not v or abs(sum(x.weight for x in v) - 100) > .01:
            raise ValueError('Scorecard weights must total 100')
        return v


class ReqIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    client: str = Field(min_length=1)
    location: str = ''
    description: str = Field(min_length=1)
    scorecard: Card


class JD(BaseModel):
    description: str = Field(min_length=20)


class Stage(BaseModel):
    stage: str


class Consent(BaseModel):
    status: Literal['Granted', 'Withdrawn', 'Pending']


class ClientAction(BaseModel):
    reason: str = Field(default='', max_length=1000)
    slots: list[str] = Field(default=[], max_length=5)


class Resolve(BaseModel):
    action: Literal['discard', 'keep_both'] = 'discard'


# ---------------------------------------------------------------- app
app = FastAPI(title='Talentra API', version='0.3.0')
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in os.getenv('CORS_ORIGINS', 'http://localhost:3000').split(',') if x.strip()], allow_methods=['*'], allow_headers=['*'])
FAILS = defaultdict(list)


@app.on_event('startup')
def startup():
    recover_pending()


@app.get('/api/health')
def health():
    # demo = the public demo accounts exist and use the documented password, so the sign-in page may offer one-click demo logins
    return {'status': 'ok', 'demo': os.getenv('SEED_DEMO', '1') != '0' and not os.getenv('DEMO_PASSWORD')}


@app.post('/api/auth/login')
def login(v: Login, d: Session = Depends(db)):
    key = v.email.lower(); t = time.time(); FAILS[key] = [x for x in FAILS[key] if t - x < 300]
    if len(FAILS[key]) >= 8:
        raise HTTPException(429, 'Too many failed attempts. Try again in a few minutes.')
    u = d.query(User).filter_by(email=key).first()
    if not u or not check_password(v.password, u.password_hash):
        FAILS[key].append(t); raise HTTPException(401, 'Invalid email or password')
    FAILS.pop(key, None)
    return {'access_token': jwt.encode({'sub': u.id, 'exp': datetime.now(timezone.utc) + timedelta(hours=8)}, SECRET, algorithm='HS256'), 'role': u.role, 'email': u.email, 'org': u.org}


# --- JD extraction
def call_llm(description):
    payload = {'model': os.environ['LLM_MODEL'], 'response_format': {'type': 'json_object'}, 'temperature': 0, 'messages': [
        {'role': 'system', 'content': 'Extract only requirements stated in the job description. Return JSON {"criteria":[{"label":str,"type":"skills|experience|notice|ctc|location|education","weight":number,"values":[str],"min":number|null,"max":number|null}]}. Use "min" (years) for experience, "max" (days) for notice and "max" (lakh per annum) for ctc. Weights must total 100. Never invent requirements.'},
        {'role': 'user', 'content': description}]}
    request = Request(os.getenv('LLM_BASE_URL', 'https://api.openai.com/v1/chat/completions'), data=json.dumps(payload).encode(), headers={'Authorization': 'Bearer ' + os.environ['LLM_API_KEY'], 'Content-Type': 'application/json'})
    return json.loads(json.loads(urlopen(request, timeout=45).read())['choices'][0]['message']['content'])


def normalize_weights(result):
    crit = result.get('criteria') or []
    tot = sum(float(x.get('weight', 0)) for x in crit)
    if not crit or tot <= 0: raise ValueError('the model returned no usable criteria')
    if abs(tot - 100) > .01:
        for x in crit: x['weight'] = round(float(x['weight']) * 100 / tot, 1)
        crit[-1]['weight'] = round(100 - sum(x['weight'] for x in crit[:-1]), 1)
        return ['Weights returned by the model did not total 100 and were scaled proportionally. Review before saving.']
    return []


@app.get('/api/jd/status')
def jd_status(u=Depends(rec)):
    return {'configured': bool(os.getenv('LLM_API_KEY') and os.getenv('LLM_MODEL'))}


@app.post('/api/jd/extract')
def jd(v: JD, u=Depends(rec)):
    if not os.getenv('LLM_API_KEY') or not os.getenv('LLM_MODEL'):
        raise HTTPException(503, 'AI extraction is not configured. Set LLM_API_KEY and LLM_MODEL on the server, or build the scorecard manually.')
    try:
        raw = call_llm(v.description); warnings = normalize_weights(raw); card = Card.model_validate(raw)
    except HTTPError as e:
        raise HTTPException(502, f'AI provider returned HTTP {e.code}. Check the API key, model name and quota.')
    except Exception as e:
        raise HTTPException(502, 'AI extraction failed or returned an invalid scorecard: ' + str(e)[:200])
    return {**card.model_dump(), 'warnings': warnings}


# --- requisitions
@app.get('/api/client-orgs')
def client_orgs(u=Depends(rec), d: Session = Depends(db)):
    return sorted({x.org for x in d.query(User).filter_by(role='CLIENT')})


@app.post('/api/requisitions')
def create(v: ReqIn, u=Depends(rec), d: Session = Depends(db)):
    org = next((x.org for x in d.query(User).filter_by(role='CLIENT') if x.org.lower() == v.client.strip().lower()), None)
    if not org:
        raise HTTPException(422, 'Unknown client organization. Clients only see requisitions that match an existing client account organization.')
    x = Requisition(id=str(uuid.uuid4()), title=v.title.strip(), client=org, location=v.location, description=v.description, scorecard=v.scorecard.model_dump())
    d.add(x); audit(d, u, 'requisition_create', x.id); d.commit(); return {'id': x.id}


@app.put('/api/requisitions/{req}/scorecard')
def update_scorecard(req: str, v: Card, u=Depends(rec), d: Session = Depends(db)):
    x = d.get(Requisition, req)
    if not x: raise HTTPException(404, 'Requisition not found')
    x.scorecard = v.model_dump(); n = 0
    for c in d.query(Candidate).filter_by(requisition_id=req).filter(Candidate.deleted_at.is_(None)):
        rescore(d, c, x); n += 1
    audit(d, u, 'scorecard_update', req); d.commit(); return {'id': x.id, 'scorecard': x.scorecard, 'rescored': n}


@app.get('/api/requisitions')
def reqs(u=Depends(rec), d: Session = Depends(db)):
    counts = defaultdict(int)
    for c in d.query(Candidate.requisition_id).filter(Candidate.deleted_at.is_(None)): counts[c[0]] += 1
    return [{'id': x.id, 'title': x.title, 'client': x.client, 'location': x.location, 'description': x.description, 'scorecard': x.scorecard, 'candidates': counts[x.id], 'created_at': x.created_at.isoformat()} for x in d.query(Requisition).order_by(Requisition.created_at.desc())]


# --- uploads, batches, documents
def magic_ok(ext, blob):
    return blob[:5] == b'%PDF-' if ext == '.pdf' else blob[:4] == b'PK\x03\x04'


@app.post('/api/requisitions/{req}/uploads')
async def upload(req: str, files: list[UploadFile] = File(...), u=Depends(rec), d: Session = Depends(db)):
    if not d.get(Requisition, req): raise HTTPException(404, 'Requisition not found')
    if not files or len(files) > 500: raise HTTPException(422, 'Upload between 1 and 500 files per batch')
    b = Batch(id=str(uuid.uuid4()), requisition_id=req); d.add(b); d.flush(); rows = []
    for f in files:
        name = Path(f.filename or 'resume').name[:200]; ext = Path(name).suffix.lower(); blob = await f.read()
        row = dict(id=str(uuid.uuid4()), batch_id=b.id, candidate_id=None, filename=name, path='', sha256=hashlib.sha256(blob).hexdigest(), status='queued', error=None)
        if ext not in ('.pdf', '.docx'): row.update(status='failed', error='Unsupported file type; only PDF and DOCX are accepted')
        elif not blob: row.update(status='failed', error='File is empty')
        elif len(blob) > MAX_BYTES: row.update(status='failed', error=f'File exceeds the {MAX_BYTES // 1048576} MB limit')
        elif not magic_ok(ext, blob): row.update(status='failed', error=f'File content is not a valid {ext[1:].upper()}')
        else:
            dest = UPLOADS / (str(uuid.uuid4()) + ext); dest.write_bytes(blob); row['path'] = str(dest)
        rows.append(Resume(**row))
    d.add_all(rows); audit(d, u, 'upload', b.id); d.commit()
    for x in rows:
        if x.status == 'queued': enqueue(x.id)
    return {'batch_id': b.id, 'accepted': sum(x.status == 'queued' for x in rows), 'rejected': sum(x.status == 'failed' for x in rows)}


STATUSES = ['queued', 'processing', 'completed', 'failed', 'duplicate', 'resolved_duplicate']


def counts_of(rows):
    c = {s: 0 for s in STATUSES}
    for x in rows:
        if x.status in c: c[x.status] += 1
    return c


@app.get('/api/batches')
def batches(u=Depends(rec), d: Session = Depends(db)):
    by = defaultdict(list)
    for x in d.query(Resume): by[x.batch_id].append(x)
    titles = {r.id: r.title for r in d.query(Requisition)}
    return [{'id': b.id, 'requisition_id': b.requisition_id, 'requisition_title': titles.get(b.requisition_id, ''), 'created_at': b.created_at.isoformat(), 'total': len(by[b.id]), 'counts': counts_of(by[b.id])} for b in d.query(Batch).order_by(Batch.created_at.desc()).limit(100)]


@app.get('/api/batches/{bid}')
def batch(bid: str, u=Depends(rec), d: Session = Depends(db)):
    b = d.get(Batch, bid)
    if not b: raise HTTPException(404, 'Batch not found')
    rows = d.query(Resume).filter_by(batch_id=bid).all()
    return {'id': bid, 'requisition_id': b.requisition_id, 'created_at': b.created_at.isoformat(), 'total': len(rows), 'counts': counts_of(rows),
            'files': [{'id': x.id, 'filename': x.filename, 'status': x.status, 'error': x.error, 'candidate_id': x.candidate_id if x.status == 'completed' else None} for x in rows]}


@app.post('/api/resumes/{rid}/retry')
def retry(rid: str, u=Depends(rec), d: Session = Depends(db)):
    r = d.get(Resume, rid)
    if not r or r.status != 'failed': raise HTTPException(404, 'Retryable document not found')
    if not r.path or not Path(r.path).exists(): raise HTTPException(422, 'The original file was rejected at upload; upload a valid file again')
    r.status = 'queued'; r.error = None; d.commit(); enqueue(rid); return {'status': 'queued'}


@app.post('/api/batches/{bid}/retry-failed')
def retry_failed(bid: str, u=Depends(rec), d: Session = Depends(db)):
    ids = []
    for r in d.query(Resume).filter_by(batch_id=bid, status='failed'):
        if r.path and Path(r.path).exists(): r.status = 'queued'; r.error = None; ids.append(r.id)
    d.commit()
    for i in ids: enqueue(i)
    return {'requeued': len(ids)}


@app.get('/api/documents/{rid}')
def document(rid: str, u=Depends(rec), d: Session = Depends(db)):
    r = d.get(Resume, rid)
    if not r or r.status == 'deleted' or not r.path or not Path(r.path).exists(): raise HTTPException(404, 'Document not found')
    audit(d, u, 'document_preview', r.candidate_id or rid); d.commit()
    mt = 'application/pdf' if r.path.endswith('.pdf') else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    return FileResponse(r.path, media_type=mt, filename=r.filename, content_disposition_type='inline')


# --- candidates
def resume_ids(d):
    return {x.candidate_id: x.id for x in d.query(Resume).filter(Resume.status == 'completed', Resume.candidate_id.isnot(None))}


def live(d, cid):
    x = d.get(Candidate, cid)
    if not x or x.deleted_at: raise HTTPException(404, 'Candidate not found')
    return x


def cv_reviewed(d, u, c):
    """A recruiter must open the original CV (or, if no file is stored, the profile) before submitting it to a client."""
    action = 'document_preview' if resume_ids(d).get(c.id) else 'candidate_view'
    return d.query(Audit).filter_by(actor_id=u.id, target=c.id, action=action).first() is not None


@app.get('/api/candidates')
def candidates(requisition_id: str | None = None, u=Depends(rec), d: Session = Depends(db)):
    q = d.query(Candidate).filter(Candidate.deleted_at.is_(None))
    if requisition_id: q = q.filter_by(requisition_id=requisition_id)
    rids = resume_ids(d); titles = {r.id: r.title for r in d.query(Requisition)}
    rows = sorted(q.all(), key=lambda z: (-z.score, z.created_at)); rank = defaultdict(int); out = []
    for z in rows:
        rank[z.requisition_id] += 1
        out.append({'id': z.id, 'name': z.name, 'role': z.role, 'requisition_id': z.requisition_id, 'requisition_title': titles.get(z.requisition_id, ''), 'rank': rank[z.requisition_id], 'experience': z.experience, 'skills': z.skills, 'notice_days': z.notice_days, 'score': z.score, 'stage': z.stage, 'confidence': z.confidence, 'consent': z.consent, 'resume_id': rids.get(z.id)})
    return out


@app.get('/api/candidates/{cid}')
def candidate(cid: str, u=Depends(rec), d: Session = Depends(db)):
    x = live(d, cid); audit(d, u, 'candidate_view', cid); d.commit()
    sub = d.query(Submission).filter_by(candidate_id=cid).first(); req = d.get(Requisition, x.requisition_id)
    res = {k: getattr(x, k) for k in ['id', 'name', 'email', 'phone', 'role', 'experience', 'skills', 'notice_days', 'score', 'stage', 'evidence', 'consent', 'confidence']}
    res.update(ctc_lpa=find_ctc(x.raw_text)[0], cv_reviewed=cv_reviewed(d, u, x), pages=x.raw_text.split('\f'), raw_text=x.raw_text.replace('\f', '\n\n'), resume_id=resume_ids(d).get(cid), requisition_title=req.title if req else '', client_org=req.client if req else '',
               submitted=bool(sub), client_reviews=[{'action': r.action, 'reason': r.reason, 'slots': r.slots, 'at': r.created_at.isoformat()} for r in d.query(ClientReview).filter_by(candidate_id=cid).order_by(ClientReview.created_at.desc())],
               deletion_request=next(({'id': r.id, 'status': r.status} for r in d.query(DeletionRequest).filter_by(candidate_id=cid, status='Requested')), None))
    return res


@app.patch('/api/candidates/{cid}/stage')
def stage(cid: str, v: Stage, u=Depends(rec), d: Session = Depends(db)):
    x = live(d, cid)
    if v.stage not in STAGES: raise HTTPException(422, 'Unknown stage')
    if v.stage == 'Submitted to Client': raise HTTPException(422, 'Use "Submit to client" so the client organization is granted access')
    x.stage = v.stage; audit(d, u, 'stage_change', cid); d.commit(); return {'stage': x.stage}


@app.put('/api/candidates/{cid}/consent')
def consent(cid: str, v: Consent, u=Depends(rec), d: Session = Depends(db)):
    x = live(d, cid); x.consent = v.status; audit(d, u, 'consent_' + v.status.lower(), cid); d.commit(); return {'consent': x.consent}


@app.post('/api/candidates/{cid}/submit')
def submit(cid: str, u=Depends(rec), d: Session = Depends(db)):
    c = live(d, cid)
    if c.consent != 'Granted': raise HTTPException(409, 'Candidate consent must be Granted before sharing a profile with a client')
    if not cv_reviewed(d, u, c): raise HTTPException(409, 'Open the original CV before submitting this candidate to the client')
    req = d.get(Requisition, c.requisition_id)
    if not d.query(Submission).filter_by(candidate_id=cid, client_org=req.client).first(): d.add(Submission(id=str(uuid.uuid4()), candidate_id=cid, client_org=req.client))
    c.stage = 'Submitted to Client'; audit(d, u, 'client_submit', cid); d.commit(); return {'status': 'submitted', 'client': req.client}


@app.delete('/api/candidates/{cid}/submit')
def withdraw(cid: str, u=Depends(rec), d: Session = Depends(db)):
    c = live(d, cid)
    d.query(Submission).filter_by(candidate_id=cid).delete(); c.stage = 'Screened'; audit(d, u, 'client_withdraw', cid); d.commit(); return {'status': 'withdrawn'}


# --- duplicates
def reason_of(x):
    m = re.search(r'\(([^)]+)\)', x.error or ''); return m.group(1) if m else ''


@app.get('/api/duplicates')
def duplicates(u=Depends(rec), d: Session = Depends(db)):
    out = []; rids = resume_ids(d)
    for x in d.query(Resume).filter_by(status='duplicate'):
        c = d.get(Candidate, x.candidate_id) if x.candidate_id else None
        out.append({'resume_id': x.id, 'filename': x.filename, 'batch_id': x.batch_id, 'detail': x.error, 'reason': reason_of(x),
                    'existing': {'id': c.id, 'name': c.name, 'email': c.email, 'score': c.score, 'stage': c.stage, 'resume_id': rids.get(c.id)} if c and not c.deleted_at else None})
    return out


@app.post('/api/resumes/{rid}/resolve-duplicate')
def resolve_duplicate(rid: str, v: Resolve | None = None, u=Depends(rec), d: Session = Depends(db)):
    x = d.get(Resume, rid)
    if not x or x.status != 'duplicate': raise HTTPException(404, 'Duplicate record not found')
    action = v.action if v else 'discard'
    if action == 'keep_both':
        if reason_of(x) == 'email': raise HTTPException(409, 'Same email address: a second candidate cannot be created. Discard the duplicate instead.')
        x.status = 'queued'; x.candidate_id = None; x.error = None; audit(d, u, 'duplicate_keep_both', rid); d.commit(); enqueue(rid, True); return {'status': 'queued'}
    if x.path: Path(x.path).unlink(missing_ok=True)
    x.status = 'resolved_duplicate'; x.path = ''; audit(d, u, 'duplicate_discarded', rid); d.commit(); return {'status': x.status}


# --- privacy: deletion workflow
def erase(d, u, c):
    for r in d.query(Resume).filter_by(candidate_id=c.id):
        if r.path: Path(r.path).unlink(missing_ok=True)
        r.path = ''; r.status = 'deleted'; r.error = None
    d.query(Submission).filter_by(candidate_id=c.id).delete(); d.query(ClientReview).filter_by(candidate_id=c.id).delete()
    c.name = 'Deleted candidate'; c.raw_text = ''; c.email = 'deleted-' + c.id + '@invalid'; c.phone = ''; c.skills = []; c.evidence = {}; c.deleted_at = now()
    for q in d.query(DeletionRequest).filter_by(candidate_id=c.id, status='Requested'): q.status = 'Completed'; q.resolved_at = now()
    audit(d, u, 'secure_delete', c.id)


@app.post('/api/candidates/{cid}/deletion-request')
def delrequest(cid: str, u=Depends(rec), d: Session = Depends(db)):
    live(d, cid)
    q = d.query(DeletionRequest).filter_by(candidate_id=cid, status='Requested').first()
    if not q: q = DeletionRequest(id=str(uuid.uuid4()), candidate_id=cid, requested_by=u.id, status='Requested'); d.add(q); audit(d, u, 'deletion_request', cid); d.commit()
    return {'status': 'requested', 'id': q.id}


@app.get('/api/deletion-requests')
def deletion_requests(u=Depends(rec), d: Session = Depends(db)):
    return [{'id': x.id, 'candidate_id': x.candidate_id, 'candidate': (d.get(Candidate, x.candidate_id).name if d.get(Candidate, x.candidate_id) else ''), 'status': x.status, 'at': x.created_at.isoformat(), 'resolved_at': x.resolved_at.isoformat() if x.resolved_at else None} for x in d.query(DeletionRequest).order_by(DeletionRequest.created_at.desc())]


@app.post('/api/deletion-requests/{qid}/{action}')
def resolve_deletion(qid: str, action: Literal['complete', 'decline'], u=Depends(rec), d: Session = Depends(db)):
    q = d.get(DeletionRequest, qid)
    if not q or q.status != 'Requested': raise HTTPException(404, 'Open deletion request not found')
    if action == 'complete': erase(d, u, d.get(Candidate, q.candidate_id))
    else: q.status = 'Declined'; q.resolved_at = now(); audit(d, u, 'deletion_declined', q.candidate_id)
    d.commit(); return {'status': q.status}


@app.delete('/api/candidates/{cid}')
def delete(cid: str, u=Depends(rec), d: Session = Depends(db)):
    erase(d, u, live(d, cid)); d.commit(); return {'status': 'deleted'}


# --- audit
def audit_rows(d, q):
    users = {x.id: x for x in d.query(User)}
    return [{'action': x.action, 'target': x.target, 'actor': users[x.actor_id].email if x.actor_id in users else x.actor_id, 'role': users[x.actor_id].role if x.actor_id in users else '', 'at': x.created_at.isoformat() + 'Z'} for x in q]


@app.get('/api/audit')
def audits(u=Depends(rec), d: Session = Depends(db)):
    return audit_rows(d, d.query(Audit).order_by(Audit.created_at.desc()).limit(200))


@app.get('/api/candidates/{cid}/audit')
def candidate_audits(cid: str, u=Depends(rec), d: Session = Depends(db)):
    return audit_rows(d, d.query(Audit).filter_by(target=cid).order_by(Audit.created_at.desc()).limit(200))


# --- client portal
EMAIL = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+'); PHONE = re.compile(r'\+?\d[\d\s().-]{8,}\d')


def mask(s):
    return PHONE.sub('[phone hidden]', EMAIL.sub('[email hidden]', s)) if s else s


def client_view(c, last):
    ev = {k: {'status': v['status'], 'quote': mask(v.get('quote')), 'page': v.get('page'), 'weight': v.get('weight'), 'points': v.get('points')} for k, v in (c.evidence or {}).items()}
    return {'id': c.id, 'name': 'Candidate ' + ref(c.id), 'role': c.role, 'experience': c.experience, 'skills': c.skills, 'notice_days': c.notice_days, 'score': c.score, 'stage': c.stage, 'evidence': ev,
            'my_review': {'action': last.action, 'reason': last.reason, 'slots': last.slots, 'at': last.created_at.isoformat() + 'Z'} if last else None}


def visible_ids(d, u):
    ids = [x.candidate_id for x in d.query(Submission).filter_by(client_org=u.org)]
    return [c for c in d.query(Candidate).filter(Candidate.id.in_(ids), Candidate.deleted_at.is_(None), Candidate.consent != 'Withdrawn')]


@app.get('/api/client/submissions')
def client(u=Depends(client_user), d: Session = Depends(db)):
    out = []
    for c in visible_ids(d, u):
        last = d.query(ClientReview).filter_by(candidate_id=c.id, client_org=u.org).order_by(ClientReview.created_at.desc()).first()
        out.append(client_view(c, last)); audit(d, u, 'client_view', c.id)
    d.commit(); return sorted(out, key=lambda x: -x['score'])


@app.post('/api/client/submissions/{cid}/{action}')
def client_action(cid: str, action: Literal['shortlist', 'reject', 'interview'], v: ClientAction, u=Depends(client_user), d: Session = Depends(db)):
    c = next((x for x in visible_ids(d, u) if x.id == cid), None)
    if not c: raise HTTPException(404, 'Submitted candidate not found')
    if action == 'reject' and not v.reason.strip(): raise HTTPException(422, 'A rejection reason is required')
    if action == 'interview':
        if not v.slots: raise HTTPException(422, 'Provide at least one interview slot')
        try:
            for s in v.slots: datetime.fromisoformat(s)
        except ValueError:
            raise HTTPException(422, 'Interview slots must be valid date-times')
    c.stage = {'shortlist': 'Shortlisted', 'reject': 'Rejected by Client', 'interview': 'Interview proposed'}[action]
    d.add(ClientReview(id=str(uuid.uuid4()), candidate_id=cid, client_org=u.org, action=action, reason=v.reason.strip() or None, slots=v.slots or None))
    audit(d, u, 'client_' + action, cid); d.commit(); return {'stage': c.stage}


# --- monitoring
def week_key(dt):
    y, w, _ = dt.isocalendar(); return f'{y}-W{w:02d}', (dt - timedelta(days=dt.weekday())).date().isoformat()


@app.get('/api/fairness')
def fairness(weeks: int = 8, u=Depends(monitor_user), d: Session = Depends(db)):
    """Compares the AI ranking with who recruiters actually selected (submitted to a client or advanced). Monitoring only."""
    cands = d.query(Candidate).filter(Candidate.deleted_at.is_(None)).all()
    submitted = {x.candidate_id for x in d.query(Submission)}; titles = {r.id: r.title for r in d.query(Requisition)}
    groups = defaultdict(list)
    for c in cands: groups[(week_key(c.created_at)[0], c.requisition_id)].append(c)
    wk = {}
    for (w, rid), cs in groups.items():
        ranked = sorted(cs, key=lambda z: (-z.score, z.created_at)); sel = [c for c in ranked if c.id in submitted or c.stage in SELECTED_STAGES]; k = len(sel)
        top = {c.id for c in ranked[:k]}; ns = [c for c in ranked if c not in sel]
        avg = lambda xs: round(sum(x.score for x in xs) / len(xs), 1) if xs else None
        rows = [{'ref': 'C-' + ref(c.id), 'ai_rank': i + 1, 'score': c.score, 'selected': c in sel, 'stage': c.stage} for i, c in enumerate(ranked)]
        diffs = [{'ref': r['ref'], 'ai_rank': r['ai_rank'], 'score': r['score'], 'kind': 'selected outside AI top-%d' % k if r['selected'] else 'in AI top-%d, not selected' % k} for r, c in zip(rows, ranked) if (r['selected'] and c.id not in top) or (not r['selected'] and c.id in top and k)]
        entry = {'requisition_id': rid, 'title': titles.get(rid, ''), 'sample_size': len(cs), 'selected': k, 'top_k': k, 'overlap_at_k': round(len(top & {c.id for c in sel}) / k, 2) if k else None,
                 'mean_ai_rank_selected': round(sum(r['ai_rank'] for r in rows if r['selected']) / k, 1) if k else None, 'avg_score_selected': avg(sel), 'avg_score_not_selected': avg(ns), 'candidates': rows, 'differences': diffs}
        wk.setdefault(w, {'week': w, 'starts': week_key(cs[0].created_at)[1], 'sample_size': 0, 'selected': 0, 'requisitions': []})
        wk[w]['sample_size'] += len(cs); wk[w]['selected'] += k; wk[w]['requisitions'].append(entry)
    out = sorted(wk.values(), key=lambda x: x['week'], reverse=True)[:max(1, min(weeks, 52))]
    sel_all = [c for c in cands if c.id in submitted or c.stage in SELECTED_STAGES]; rest = [c for c in cands if c not in sel_all]
    avg = lambda xs: round(sum(x.score for x in xs) / len(xs), 1) if xs else None
    return {'sample_size': len(cands), 'recruiter_selected': len(sel_all), 'average_ai_score': avg(cands), 'selected_average_ai_score': avg(sel_all), 'not_selected_average_ai_score': avg(rest), 'weeks': out, 'min_reliable_sample': 30,
            'note': 'Monitoring only; this does not prove the AI is unbiased. Protected attributes are excluded from scoring and are not collected, so group-level disparity cannot be measured here. Small samples are noisy. Candidates with equal scores are ordered by processing time, so rank differences among tied scores are not meaningful.'}


@app.get('/api/dashboard')
def dashboard(u=Depends(rec), d: Session = Depends(db)):
    x = d.query(Candidate).filter(Candidate.deleted_at.is_(None)).all(); res = d.query(Resume).all()
    return {'active_requisitions': d.query(Requisition).count(), 'candidates_processed': len(x), 'awaiting_review': sum(z.stage in ('Sourced', 'Screened') for z in x), 'submitted_to_client': sum(z.stage == 'Submitted to Client' for z in x), 'shortlisted': sum(z.stage == 'Shortlisted' for z in x),
            'documents_processing': sum(r.status in ('queued', 'processing') for r in res), 'documents_failed': sum(r.status == 'failed' for r in res), 'duplicates_to_review': sum(r.status == 'duplicate' for r in res), 'open_deletion_requests': d.query(DeletionRequest).filter_by(status='Requested').count()}


# ---------------------------------------------------------------- seed (synthetic demo data; disable with SEED_DEMO=0)
SEED_CVS = [  # (candidate id, requisition key, file name, CV lines) - names/roles/skills/notice from the client brief; the rest is invented
    ('CND-91022', 'java', 'ritika_bansal.docx', ['Ritika Bansal', 'ritika.bansal@example.com | +91 9000000101 | Noida', 'Senior Java Developer', '6.5 years of experience in backend engineering', 'Skills: Java, Spring Boot, microservices, Kafka, SQL', 'Built payment microservices with Spring Boot for a retail bank.', 'Expected CTC: 24 LPA', 'Notice period: 60 days']),
    ('CND-91047', 'kyc', 'arjun_rawat.docx', ['Arjun Rawat', 'arjun.rawat@example.com | 9000000102', 'KYC Analyst', '3 years of experience in banking back-office operations', 'Skills: KYC, AML checks, Excel', 'Reviewed customer onboarding files and AML alerts.', 'Expected CTC: 6 LPA', 'Notice period: 30 days']),
    ('CND-91088', 'java', 'pooja_nair.docx', ['Pooja Nair', 'pooja.nair@example.com | 9000000103', 'Java Developer', '4 years of experience', 'Skills: Java, Hibernate, REST APIs', 'Maintained REST services for an insurance platform.', 'Expected CTC: 14 LPA', 'Notice period: 90 days']),
]


def seed():
    if os.getenv('SEED_DEMO', '1') == '0': return
    d = SessionLocal()
    try:
        if d.query(User).first(): return
        pw = hash_password(os.getenv('DEMO_PASSWORD', 'DemoPass123!'))
        d.add_all([User(id='u-rec', email='recruiter@talentra.demo', role='RECRUITER', org='Talentra', password_hash=pw), User(id='u-client', email='client@acme.demo', role='CLIENT', org='Acme Systems', password_hash=pw),
                   User(id='u-client2', email='client@globex.demo', role='CLIENT', org='Globex Corp', password_hash=pw), User(id='u-head', email='head@talentra.demo', role='DELIVERY_HEAD', org='Talentra', password_hash=pw)])
        reqs = {
            'java': Requisition(id='req-java', title='Senior Java Developer', client='Acme Systems', location='Noida', description='Senior Java Developer, 5-8 years, Spring Boot, Noida, notice up to 60 days.',
                                scorecard={'criteria': [{'label': 'Must-have skills', 'type': 'skills', 'values': ['Java', 'Spring Boot', 'Microservices'], 'weight': 45}, {'label': 'Experience (5+ yrs)', 'type': 'experience', 'min': 5, 'weight': 25}, {'label': 'Notice up to 60 days', 'type': 'notice', 'max': 60, 'weight': 15}, {'label': 'Location', 'type': 'location', 'values': ['Noida'], 'weight': 5}, {'label': 'Expected CTC up to 28 LPA', 'type': 'ctc', 'max': 28, 'weight': 10}]}),
            'kyc': Requisition(id='req-kyc', title='KYC Analyst', client='Globex Corp', location='Noida', description='KYC Analyst for banking back-office. KYC, AML checks and Excel; 2+ years; notice up to 45 days.',
                               scorecard={'criteria': [{'label': 'Must-have skills', 'type': 'skills', 'values': ['KYC', 'AML checks', 'Excel'], 'weight': 60}, {'label': 'Experience (2+ yrs)', 'type': 'experience', 'min': 2, 'weight': 25}, {'label': 'Notice up to 45 days', 'type': 'notice', 'max': 45, 'weight': 15}]})}
        d.add_all(reqs.values()); d.flush(); folder = UPLOADS; rows = []
        for cid, key, name, lines in SEED_CVS:
            doc = Document()
            for line in lines: doc.add_paragraph(line)
            dest = folder / (str(uuid.uuid4()) + '.docx'); doc.save(dest); blob = dest.read_bytes()
            b = Batch(id='seed-' + key, requisition_id=reqs[key].id)
            if not d.get(Batch, b.id): d.add(b); d.flush()
            rows.append((cid, Resume(id=str(uuid.uuid4()), batch_id=b.id, filename=name, path=str(dest), sha256=hashlib.sha256(blob).hexdigest(), status='queued')))
        d.add_all([r for _, r in rows]); d.commit()
        for cid, r in rows: process(r.id, cid=cid)  # the real parse + score pipeline
        c = d.get(Candidate, 'CND-91022')
        if c:  # one candidate already shared with the client, so the portal is not empty
            c.consent = 'Granted'; c.stage = 'Submitted to Client'; d.add(Submission(id=str(uuid.uuid4()), candidate_id=c.id, client_org='Acme Systems'))
        d.commit()
    finally:
        d.close()


seed()
