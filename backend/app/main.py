from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.categories import router as categories_router
from app.api.health import router as health_router
from app.api.me import router as me_router
from app.api.profile import router as profile_router
from app.api.statements import router as statements_router
from app.api.transactions import router as transactions_router
from app.core.config import settings

app = FastAPI(title="PennyPilot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(me_router)
app.include_router(profile_router)
app.include_router(statements_router)
app.include_router(transactions_router)
app.include_router(categories_router)
