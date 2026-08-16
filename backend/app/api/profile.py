import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.user import User
from app.schemas.profile import ProfileRead, ProfileUpdate
from app.services.storage import upload_avatar

router = APIRouter()


def _get_or_create(user_id: uuid.UUID, db: Session) -> User:
    profile = db.get(User, user_id)
    if profile is None:
        profile = User(user_id=user_id)
        db.add(profile)
    return profile


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
    profile = _get_or_create(uuid.UUID(user.id), db)

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


@router.post("/api/profile/image", response_model=ProfileRead)
def upload_profile_image(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    data = file.file.read()
    public_url = upload_avatar(
        user_id=user.id,
        token=user.token,
        content_type=file.content_type or "",
        data=data,
    )

    profile = _get_or_create(uuid.UUID(user.id), db)
    profile.profile_image = public_url
    db.commit()
    db.refresh(profile)
    return profile
