import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.user import User
from app.schemas.profile import ProfileRead, ProfileUpdate

router = APIRouter()


@router.get("/api/profile", response_model=ProfileRead)
def get_profile(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User | ProfileRead:
    profile = db.get(User, uuid.UUID(user.id))
    return profile if profile is not None else ProfileRead()


@router.put("/api/profile", response_model=ProfileRead)
def update_profile(
    payload: ProfileUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    user_id = uuid.UUID(user.id)
    profile = db.get(User, user_id)
    if profile is None:
        profile = User(user_id=user_id)
        db.add(profile)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username already taken"
        ) from exc

    db.refresh(profile)
    return profile
