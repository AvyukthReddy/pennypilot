import time

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

AVATAR_BUCKET = "avatars"
MAX_AVATAR_BYTES = 5 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def upload_avatar(user_id: str, token: str, content_type: str, data: bytes) -> str:
    """Uploads an avatar to the user's own folder in the `avatars` bucket, enforced by
    Supabase Storage RLS (the same user JWT used against Postgres). Returns the public
    URL, cache-busted so the browser picks up replacements immediately."""
    ext = ALLOWED_CONTENT_TYPES.get(content_type)
    if ext is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Image must be JPEG, PNG, or WebP",
        )
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Image must be 5MB or smaller",
        )

    object_path = f"{user_id}/avatar.{ext}"
    response = httpx.post(
        f"{settings.supabase_url}/storage/v1/object/{AVATAR_BUCKET}/{object_path}",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": settings.supabase_publishable_key,
            "Content-Type": content_type,
            "x-upsert": "true",
        },
        content=data,
    )
    if response.is_error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Image upload failed"
        )

    return f"{settings.supabase_url}/storage/v1/object/public/{AVATAR_BUCKET}/{object_path}?v={int(time.time())}"
