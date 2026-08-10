from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.me import router as me_router

app = FastAPI(title="PennyPilot API")

app.include_router(health_router)
app.include_router(me_router)
