import os, sys, tempfile, time
from pathlib import Path
_tmp = tempfile.mkdtemp()
os.environ.update(TALENTRA_NO_DOTENV='1', DATABASE_URL=f'sqlite:///{_tmp}/test.db', UPLOAD_DIR=f'{_tmp}/uploads', JWT_SECRET='x' * 40, LLM_API_KEY='', LLM_MODEL='', PROCESS_WORKERS='3')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import io, pytest, fitz
from docx import Document
from fastapi.testclient import TestClient
from app import main

@pytest.fixture(scope='session')
def client():
    return TestClient(main.app)

def login(client, email, pw='DemoPass123!'):
    r = client.post('/api/auth/login', json={'email': email, 'password': pw}); assert r.status_code == 200, r.text
    return {'Authorization': 'Bearer ' + r.json()['access_token']}

@pytest.fixture(scope='session')
def rec(client): return login(client, 'recruiter@talentra.demo')
@pytest.fixture(scope='session')
def acme(client): return login(client, 'client@acme.demo')
@pytest.fixture(scope='session')
def globex(client): return login(client, 'client@globex.demo')
@pytest.fixture(scope='session')
def head(client): return login(client, 'head@talentra.demo')

def make_docx(*lines):
    d = Document()
    for l in lines: d.add_paragraph(l)
    b = io.BytesIO(); d.save(b); return b.getvalue()

def make_pdf(*lines):
    doc = fitz.open(); page = doc.new_page(); page.insert_text((72, 72), '\n'.join(lines)); return doc.tobytes()

def wait_batch(client, rec, bid, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        b = client.get(f'/api/batches/{bid}', headers=rec).json()
        if not b['counts']['queued'] and not b['counts']['processing']: return b
        time.sleep(.2)
    raise AssertionError('batch did not finish')
