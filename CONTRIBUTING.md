# Contributing

## Branch strategy

Trunk-based development:

- `main` is always deployable.
- Work happens on short-lived feature branches: `feature/<short-description>`,
  `fix/<short-description>`.
- Open a PR against `main`; CI must pass before merge.
- Merge via **squash-merge** to keep `main` history linear.
- Delete branches after merge.

## Commits

Use imperative, present-tense commit messages (e.g. "Add health check
endpoint" not "Added health check endpoint"). Keep commits focused.

## Pull requests

- Fill out the PR template (summary, changes, test plan).
- Link the related issue if one exists.
- Keep PRs small and scoped to one concern where possible.

## Local checks before opening a PR

```bash
# frontend
cd frontend && npm run lint && npx tsc --noEmit

# backend (activate the venv first: .venv\Scripts\activate on Windows,
# source .venv/bin/activate on macOS/Linux)
cd backend && ruff check . && pytest -q

# worker
cd worker && poetry run ruff check .

# full stack
docker compose --env-file .env -f docker/docker-compose.yml up --build
```
