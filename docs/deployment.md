# Deployment (Talentra)

Repository: https://github.com/urumb/talentra-ai-recruitment
Live app: **not deployed**. It runs locally with the steps below. A free-tier recipe is included at the end; it has not been tried on a host.

## Demo logins (synthetic data only)

All accounts use the password `DemoPass123!` (set by `DEMO_PASSWORD`; the seed only runs on an empty database and can be turned off with `SEED_DEMO=0`).

| Role | Email | What to try |
|---|---|---|
| Recruiter | `recruiter@talentra.demo` | Everything on the recruiter workspace |
| Client hiring manager (Acme Systems) | `client@acme.demo` | Sees only candidates submitted to Acme; shortlist, reject with reason, propose slots |
| Client hiring manager (Globex Corp) | `client@globex.demo` | Sees nothing from Acme (isolation check) |
| Delivery head | `head@talentra.demo` | Monitoring screen only |

Seeded data: the three candidates from the brief (Ritika Bansal, Arjun Rawat, Pooja Nair) are created by running generated CVs through the real parser and scorer. Two requisitions exist (Senior Java Developer for Acme, KYC Analyst for Globex). Ritika is already submitted to Acme. Extra CVs to try the bulk upload are in `sample_cvs/` (see `sample_cvs/README.md`).

## Run locally, step by step

Requirements: Python 3.12, Node 20+ (24 tested), optional Tesseract OCR for scanned PDFs. All free.

```bash
# 1. Backend (terminal 1)
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000     # uses a local SQLite file and ./uploads

# 2. Frontend (terminal 2)
cd frontend
npm install
npm run dev                         # http://localhost:3000
```

Open http://localhost:3000 and sign in with a demo login. API docs: http://localhost:8000/docs.

### Free AI for JD extraction (Groq)

1. Create a free key at https://console.groq.com (API Keys).
2. Open the file `.env` in the repository root (create it by copying `.env.example` if it does not exist). It is git-ignored.
3. Fill in these three lines (the model name must be one listed in the Groq console; `llama-3.3-70b-versatile` was valid when this was written):
   ```
   LLM_API_KEY=paste-your-key-here
   LLM_MODEL=llama-3.3-70b-versatile
   LLM_BASE_URL=https://api.groq.com/openai/v1/chat/completions
   ```
4. Restart the backend. The Requisitions screen then enables **Extract scorecard with AI** (use the "Use example JD" button to try it). Do not paste the key into any committed file.

### Tesseract OCR (only needed for scanned PDFs)

Tesseract is a free open-source OCR engine. Text PDFs and DOCX never need it.
- **Windows:** `winget install UB-Mannheim.TesseractOCR` (or the installer from the UB Mannheim page). The backend finds `C:\Program Files\Tesseract-OCR\tesseract.exe` automatically; if you installed elsewhere set `TESSERACT_CMD` in `.env`. Also run `pip install -r backend/requirements.txt` so the Python wrapper `pytesseract` is present.
- **Linux/Docker:** `apt install tesseract-ocr` (the backend Docker image already includes it).
- Check it: upload `sample_cvs/scanned_amit_verma.pdf`; it should complete and rank instead of failing with "Tesseract is not available".

Optional features:
- **Scanned PDFs:** install Tesseract (Windows installer from the UB Mannheim build, or `apt install tesseract-ocr`) and make sure `tesseract` is on PATH. Without it, scanned PDFs fail with a clear per-file message; everything else works.
- **AI JD extraction:** get a free key from an OpenAI-compatible provider (for example Google AI Studio's OpenAI-compatible endpoint or Groq), then set `LLM_API_KEY`, `LLM_MODEL` and `LLM_BASE_URL` before starting the backend. Without them the Requisitions screen says AI is not configured and you can build the scorecard by hand.

Run the tests and checks:

```bash
cd backend && python -m pytest -q       # 32 tests, LLM and OCR engine mocked
cd frontend && npm run build            # type-check + production build
docker compose config -q                # validate the compose file
```

## Run with Docker Compose

```bash
cp .env.example .env          # Windows: copy .env.example .env, then edit JWT_SECRET and POSTGRES_PASSWORD
docker compose up --build
```

Frontend http://localhost:3000, API http://localhost:8000. The backend image installs Tesseract. Volumes: `postgres_data` and `uploads`.

## Environment variables (names only; never commit values)

| Variable | Used by | Purpose |
|---|---|---|
| `JWT_SECRET` | backend | Signs login tokens (32+ random characters in production) |
| `APP_ENV` | backend | `production` refuses a weak `JWT_SECRET` |
| `DATABASE_URL` | backend | Database connection (defaults to a local SQLite file) |
| `CORS_ORIGINS` | backend | Comma-separated browser origins allowed to call the API |
| `UPLOAD_DIR`, `UPLOAD_MAX_MB`, `PROCESS_WORKERS` | backend | Where CVs are stored, size limit, parallel processing threads |
| `SEED_DEMO`, `DEMO_PASSWORD` | backend | Demo data on or off, and its password (a custom `DEMO_PASSWORD` hides the one-click demo buttons) |
| `NEXT_PUBLIC_DEMO_LOGINS` | frontend | `0` hides the one-click demo sign-in buttons (build time) |
| `TESSERACT_CMD` | backend | Full path to `tesseract.exe` if it is not on PATH (optional) |
| `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL` | backend | JD extraction (optional) |
| `POSTGRES_PASSWORD` | compose | Password of the compose database |
| `NEXT_PUBLIC_API_URL` | frontend | Public API URL, **baked in at build time** |

## Production notes

- Set `APP_ENV=production`, a long random `JWT_SECRET` and `SEED_DEMO=0`, then create users with
  `python -m app.manage create-user EMAIL ROLE ORG` (roles: `RECRUITER`, `CLIENT`, `DELIVERY_HEAD`; the password is read from `TALENTRA_PASSWORD` or prompted). A requisition's client name must equal a client user's organization.
- Terminate TLS in front of both services and restrict `CORS_ORIGINS`.
- CVs are stored unencrypted on the uploads volume: encrypt the volume and add malware scanning before real use.
- The worker pool is in-process (one API instance). Use a shared queue before scaling out.
- The schema is created on startup and there are no migrations.

## Free-tier hosting recipe (untested)

Everything below has a free plan; check each provider's current limits.

1. **Database:** a free Postgres (for example Neon or Supabase). Set `DATABASE_URL` to `postgresql+psycopg://...` (connection string from the provider).
2. **Backend:** a free Docker web service (for example Render) using `backend/Dockerfile`, with the backend environment variables above. Free instances sleep when idle (the first request can take about a minute) and their disk may be wiped on restart, so seeded CVs are recreated only if the database is empty.
3. **Frontend:** a free Next.js host (for example Vercel) with root directory `frontend` and `NEXT_PUBLIC_API_URL` set to the backend's public URL. Then set the backend's `CORS_ORIGINS` to the frontend URL and redeploy.
