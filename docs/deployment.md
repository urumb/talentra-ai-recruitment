# Deployment

## Docker Compose (single host)

1. `cp .env.example .env` and set at least `JWT_SECRET` (32+ random chars; `openssl rand -hex 32`), `POSTGRES_PASSWORD`, `CORS_ORIGINS` and `NEXT_PUBLIC_API_URL` to your real public URLs. `NEXT_PUBLIC_API_URL` is baked into the frontend at **build** time — rebuild after changing it.
2. Set `APP_ENV=production` (the API refuses to start with the development secret) and `SEED_DEMO=0`.
3. `docker compose up --build -d`
4. Create the first users (the demo seed is off):
   ```bash
   docker compose exec -e TALENTRA_PASSWORD='a-long-unique-password' backend python -m app.manage create-user you@company.com RECRUITER "Your Company"
   docker compose exec -e TALENTRA_PASSWORD='...' backend python -m app.manage create-user hiring@client.com CLIENT "Client Org Name"
   ```
   Roles: `RECRUITER`, `CLIENT`, `DELIVERY_HEAD`. A requisition's client name must match a client user's organization exactly (case-insensitive) — that is how client isolation works.
5. Optional JD extraction: set `LLM_API_KEY`, `LLM_MODEL` (and `LLM_BASE_URL` for non-OpenAI providers).

Volumes: `postgres_data` (database) and `uploads` (original CVs). Back up both; deleting a candidate removes their CV file from `uploads`.

## Production hardening checklist

- Terminate TLS in front of both services; restrict `CORS_ORIGINS` to the frontend origin.
- Encrypt the uploads volume (or move to private encrypted object storage); add malware scanning for uploads.
- Add rate limiting at the proxy (the API only throttles repeated failed logins per email, in memory).
- Use managed PostgreSQL with backups; add migrations (Alembic) before changing the schema.
- Run more than one API instance only after replacing the in-process worker pool with a shared queue (duplicate detection is serialized per process).
- JWTs last 8 hours and are held in `sessionStorage`; there is no refresh or revocation.
- Real-provider LLM extraction should be tried with your key before go-live; automated tests mock the provider.
