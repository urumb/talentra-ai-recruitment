# Technical Design Document

## Architecture
Next.js App Router provides the responsive recruiter and client experiences. FastAPI exposes typed REST endpoints and OpenAPI documentation. SQLAlchemy persists normalized entities; PostgreSQL is the production datastore. Docker Compose coordinates the stack. The development seed uses synthetic data only.

## Workflow
Recruiters create a requisition and editable 100%-weighted scorecard, then upload documents asynchronously (the production worker boundary is intentionally documented as the next increment). Parsers extract candidate fields with text offsets/page metadata. A deterministic scorer joins only non-protected extracted fields against criterion rules, saving supporting evidence. Recruiters review a CV before submission; clients see only organization-scoped, masked profiles.

## Explainability and fairness
The scoring function accepts skills, experience, notice period and CV evidence—not names, age, gender, contact details, photos or other protected information. Facts a CV does not state are labelled `unknown` (earning no points but never counting as a rejection); skills/locations that are absent are `not_found`. Nothing is fabricated. A score cannot automatically reject a person. Ranking is reproducible for a given profile and scorecard.

## Security and privacy
JWT role checks occur server-side. Production configuration requires a strong environment secret, encrypted object storage, upload malware scanning, rate limiting, audit logging, consent/deletion workflows and Alembic migrations. The MVP demonstrates authorization and consent state; it does not claim compliance certification.

## Limits and next work
Implemented: PDF/DOCX parsing with Tesseract OCR for scanned PDFs, a bounded thread-pool processor with restart recovery, rule-based candidate extraction, evidence-bearing deterministic scoring with page numbers, duplicate review, consent-gated client submission, organization-scoped masked client portal, deletion workflow that erases data and files, and an access audit. Not implemented: a durable queue (Celery/RQ), migrations, encrypted file storage, malware scanning, LLM-based candidate extraction, token revocation, and protected-attribute data for true group-fairness metrics.
