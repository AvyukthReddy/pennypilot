import os

# Tests never connect to a real database (DB sessions are mocked throughout),
# but worker.config/worker.db need DATABASE_URL to exist at import time. Real
# deployments get it from docker-compose.yml's env_file — this is a
# test-only stand-in, set before any test module imports worker.db.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
