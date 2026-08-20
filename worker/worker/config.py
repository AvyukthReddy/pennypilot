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
# transaction_region_detection.py. Defaults point at Hugging Face's Inference
# Providers router with Qwen2.5-VL-7B-Instruct, served by the "fal" provider —
# featherless-ai (the first one tried) started returning 503 capacity_exhausted
# under normal use; fal is what's confirmed working today. Override any of the
# three independently.
AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://router.huggingface.co/v1")
# Falls back to HF_TOKEN for now, since Hugging Face is the default provider and
# that's the token name their own docs/CLI use — set MODEL_API_KEY explicitly once
# you're pointing at a different provider.
MODEL_API_KEY = os.environ.get("MODEL_API_KEY") or os.environ.get("HF_TOKEN") or None
AI_MODEL = os.environ.get("AI_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct:fal")


def default_ai_provider_config() -> AIProviderConfig:
    return AIProviderConfig(base_url=AI_BASE_URL, api_key=MODEL_API_KEY, model=AI_MODEL)
