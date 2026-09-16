from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.schemas.merchant import MerchantNormalizeRequest, MerchantRead
from app.services.merchant_normalization import resolve_merchant

router = APIRouter()


@router.post("/api/merchants/normalize", response_model=MerchantRead)
def normalize_merchant(
    payload: MerchantNormalizeRequest,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MerchantRead:
    """Manual verification endpoint only; not called from statement ingestion or
    any other pipeline yet. Requires auth like every other route, but merchants
    are global and this doesn't scope by user."""
    merchant = resolve_merchant(db, payload.description)
    return MerchantRead.model_validate(merchant)
