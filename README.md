# PennyPilot

An AI Financial Copilot — a full-stack SaaS for tracking spending, connecting
bank accounts, ingesting statements/receipts via OCR, and using AI for
transaction categorization, budgeting insights, forecasting, anomaly
detection, and a RAG-powered chat assistant over your own financial data.

This repo is in **Phase 0 (Foundation)**: repo structure, local dev
environment, and CI/CD are in place. Feature work (auth, Plaid, OCR, AI
categorization, etc.) lands in subsequent phases.

## Tech stack

| Layer     | Tech |
|-----------|------|
| Frontend  | Next.js (App Router), TypeScript, Tailwind CSS |
| Backend   | FastAPI (Python) |
| Worker    | Celery + Redis |
| Database  | PostgreSQL, Redis |
| Infra     | Docker Compose (local), GitHub Actions (CI) |

## Repository structure

```
pennypilot/
  frontend/    Next.js app
  backend/     FastAPI app
  worker/      Celery worker
  shared/      Code shared between backend and worker
  docs/        Design docs, architecture notes
  docker/      docker-compose.yml
  scripts/     Dev/ops scripts
```

## Local development

Requires Docker Desktop.

```bash
cp .env.example .env
docker compose -f docker/docker-compose.yml up --build
```

- Frontend: http://localhost:3000
- Backend health check: http://localhost:8000/health

### Running services individually

**Frontend**
```bash
cd frontend
pnpm install
pnpm dev
```

**Backend**
```bash
cd backend
poetry install
poetry run uvicorn app.main:app --reload
```

**Worker**
```bash
cd worker
poetry install
poetry run celery -A worker.celery_app worker --loglevel=info
```

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for branch strategy and PR conventions.
