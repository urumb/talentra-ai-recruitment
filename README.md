# Talentra — AI-assisted recruitment screening

An evidence-first recruitment screening MVP. It intentionally uses deterministic scoring: AI/extraction can enrich a profile, but the numeric score is calculated from the scorecard and CV evidence only. Scores are decision-support signals, never rejection decisions.

## Quick start

```bash
docker compose up --build
```

Open `http://localhost:3000`. The API documentation is at `http://localhost:8000/docs`.

Demo accounts: `recruiter@talentra.demo` / `DemoPass123!` and `client@acme.demo` / `DemoPass123!`.

For local backend development: `cd backend; python -m venv .venv; .venv\\Scripts\\pip install -r requirements.txt; .venv\\Scripts\\uvicorn app.main:app --reload`. Set `DATABASE_URL` to a PostgreSQL URL for production; SQLite is used only as a development fallback.

See [docs/technical-design.md](docs/technical-design.md) and [docs/deployment.md](docs/deployment.md).

## Screening workflows

Recruiters can create requisitions with a scorecard whose weights must total 100, upload up to 500 PDF or DOCX CVs, inspect per-file batch status, retry failures, review duplicates, and preview the original document. Parsing uses PyMuPDF and python-docx; scanned PDFs require a local Tesseract installation in addition to the Python OCR packages.

Set `LLM_API_KEY`, `LLM_MODEL`, and optionally `LLM_BASE_URL` before using JD extraction. When no provider is configured, the API deliberately returns a configuration error so recruiters can create the scorecard manually. Scores are deterministic and retain criterion evidence, source document, page, and confidence fields. Candidate documents and profiles are access-audited; client records are only returned through explicit submissions for that client organization.
