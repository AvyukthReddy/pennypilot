import os
from pathlib import Path

from dotenv import load_dotenv

# Auto-loads the repo-root .env (same file backend/ reads) so DATABASE_URL
# doesn't need to be exported by hand on every local run. Does NOT override
# a variable already set in the shell — REDIS_URL in .env is the
# Docker-network hostname ("redis"), which local (non-Docker) runs must
# still override manually to "localhost" before starting this process.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
