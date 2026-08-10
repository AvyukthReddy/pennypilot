from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, get_current_user

router = APIRouter()


@router.get("/api/me")
def me(user: CurrentUser = Depends(get_current_user)) -> dict[str, str | None]:
    return {"id": user.id, "email": user.email}
