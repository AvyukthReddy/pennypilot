import os
from pathlib import Path

from dotenv import load_dotenv

from worker.ai_provider import AIProviderConfig

# Auto-loads the repo-root .env (same file backend/ reads) so DATABASE_URL
# doesn't need to be exported by hand on every local run. Does NOT override
# a variable already set in the shell — REDIS_URL in .env is the
# Docker-network hostname ("redis"), which local (non-Docker) runs must
# still override manually to "localhost" before starting this process.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Document understanding — all provider-specific. Swapping models or providers
# (to benchmark, or because a free tier changed) is an env change only, never a
# code change in worker/worker/document_understanding.py or
# transaction_region_detection.py. MODEL_PROVIDER picks which pair of
# <PROVIDER>_BASE_URL/<PROVIDER>_API_KEY vars to read; unset or unrecognized
# falls back to Hugging Face, since that's the confirmed-working default.
MODEL_PROVIDER = os.environ.get("MODEL_PROVIDER", "HUGGINGFACE").upper()

if MODEL_PROVIDER == "OPENROUTER":
    AI_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    MODEL_API_KEY = os.environ.get("OPENROUTER_API_KEY") or None
else:  # "HUGGINGFACE" or anything unrecognized
    AI_BASE_URL = os.environ.get("HUGGINGFACE_BASE_URL", "https://router.huggingface.co/v1")
    MODEL_API_KEY = os.environ.get("HUGGINGFACE_API_KEY") or os.environ.get("HF_TOKEN") or None

AI_MODEL = os.environ.get("AI_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct:fal")


def default_ai_provider_config() -> AIProviderConfig:
    return AIProviderConfig(base_url=AI_BASE_URL, api_key=MODEL_API_KEY, model=AI_MODEL)
