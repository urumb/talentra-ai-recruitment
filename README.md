# Talentra — evidence-first recruitment screening

Talentra is a recruitment screening app with a recruiter workspace, a privacy-masked client portal and a delivery-head monitoring view. **Scores are deterministic**: a saved scorecard is applied to text found in the CV, and every criterion carries a verbatim quote, source file and page. AI is used only to draft a scorecard from a job description. Nobody is ever rejected automatically, and facts a CV does not state are shown as *unknown* (0 points, never a failure).

Stack: FastAPI + SQLAlchemy (PostgreSQL; SQLite for local dev) · Next.js 15 · PyMuPDF / python-docx / Tesseract OCR.

## What you can do

**Recruiter** — create requisitions; extract a scorecard from a JD with an LLM and edit criteria/weights (must total 100); bulk-upload up to 500 PDF/DOCX CVs; follow per-batch and per-document progress (total / completed / processing / failed / duplicate), see each error and retry failures; review ranked candidates with criterion-level evidence; preview the original CV; resolve duplicates; record consent; submit to the client (only with consent *Granted*); track the pipeline; run the deletion workflow; inspect the access audit.
**Client** — sees only candidates submitted to their own organization, with name and contact details withheld; can shortlist, reject (reason required) or propose up to 5 interview slots. Actions persist and appear in the recruiter's pipeline and candidate feedback tab.
**Delivery head** — weekly comparison of the AI ranking with recruiter selections (sample size, overlap with AI top-K, mean AI rank of selected, ranking differences). This is monitoring, **not proof the AI is unbiased**; no protected attributes are collected, so group-level disparity can't be measured.

Sample CVs for trying the bulk upload (text, table, scanned, duplicate and corrupt files) are in [sample_cvs/](sample_cvs/README.md). Design document: [docs/Talentra_Technical_Design_Document.docx](docs/Talentra_Technical_Design_Document.docx).

## Run with Docker

```bash
cp .env.example .env      # PowerShell: copy .env.example .env   — then edit JWT_SECRET etc.
docker compose up --build
```

Open http://localhost:3000 (API docs: http://localhost:8000/docs). Tesseract is installed in the backend image.

Demo accounts (synthetic data incl. the brief's three candidates; password `DemoPass123!` unless `DEMO_PASSWORD` is set):
`recruiter@talentra.demo` · `client@acme.demo` · `client@globex.demo` (second org, for isolation checks) · `head@talentra.demo` (delivery head).

## Run locally (no Docker)

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000   # SQLite file + ./uploads by default

cd frontend
npm install
npm run dev                                           # http://localhost:3000
```

Scanned PDFs need the Tesseract binary on PATH (`apt install tesseract-ocr`, or the Windows installer). Without it those documents fail with a clear per-file error; text PDFs and DOCX are unaffected.

## Tests

```bash
cd backend && python -m pytest -q        # API, security, scoring, processing (LLM and OCR engine mocked)
cd frontend && npm run build             # type-check + production build
docker compose config -q                 # validate compose
```

## Configuration

See [.env.example](.env.example). Key variables: `JWT_SECRET`, `DATABASE_URL`, `CORS_ORIGINS`, `NEXT_PUBLIC_API_URL` (build-time), `LLM_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL` (any OpenAI-compatible chat-completions endpoint), `UPLOAD_MAX_MB`, `PROCESS_WORKERS`, `SEED_DEMO`. Without LLM settings, JD extraction reports that AI isn't configured and manual scorecards keep working.

## Limits to know about

- Candidate fields (name, email, phone, years of experience, notice period, skills) come from **rule-based extraction**, not an LLM. The name is only taken when the first CV line looks like a name; otherwise it is "Unnamed candidate".
- Background processing is an in-process thread pool (`PROCESS_WORKERS`); unfinished documents are re-queued on restart. For multi-instance deployment use a real queue.
- No database migrations are included; the schema is created on startup. Upgrading from the earlier MVP schema requires a fresh database.
- Uploaded CVs are stored unencrypted on the `uploads` volume; use encrypted storage in production. See [docs/deployment.md](docs/deployment.md) and [docs/technical-design.md](docs/technical-design.md).
