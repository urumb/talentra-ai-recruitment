# Deployment

1. Copy `.env.example` to `.env` and replace `JWT_SECRET`; provide a PostgreSQL `DATABASE_URL`.
2. Run `docker compose up --build`.
3. Visit `http://localhost:3000`; API OpenAPI docs are at `http://localhost:8000/docs`.

For production, use managed PostgreSQL, private encrypted object storage, a secret manager, TLS termination, a background worker and database backups. Do not deploy the example password or development JWT secret.
