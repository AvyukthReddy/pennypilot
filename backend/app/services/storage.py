import time
import uuid

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

STATEMENT_BUCKET = "statements"
MAX_STATEMENT_BYTES = 20 * 1024 * 1024
ALLOWED_STATEMENT_TYPES = {
    "application/pdf": "pdf",
    "text/csv": "csv",
    "application/vnd.ms-excel": "csv",
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


def upload_statement(
    user_id: str, statement_id: uuid.UUID, token: str, content_type: str, data: bytes
) -> str:
    """Uploads a statement file to the user's own folder in the `statements` bucket,
    enforced by Supabase Storage RLS (same user-JWT trust model as avatars). The bucket
    is private — unlike avatars, no public URL is returned. Returns the storage object
    path, which is what gets persisted as `Statement.storage_path`."""
    ext = ALLOWED_STATEMENT_TYPES.get(content_type)
    if ext is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Statement must be a PDF or CSV file",
        )
    if len(data) > MAX_STATEMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Statement must be 20MB or smaller",
        )

    object_path = f"{user_id}/{statement_id}.{ext}"
    response = httpx.post(
        f"{settings.supabase_url}/storage/v1/object/{STATEMENT_BUCKET}/{object_path}",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": settings.supabase_publishable_key,
            "Content-Type": content_type,
        },
        content=data,
    )
    if response.is_error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Statement upload failed"
        )

    return object_path


def get_statement_view_url(token: str, storage_path: str, expires_in: int = 120) -> str:
    """Returns a short-lived signed URL for viewing/downloading a statement file
    straight from Supabase Storage — the bucket is private, so there is no standing
    public URL to hand back the way avatars have."""
    response = httpx.post(
        f"{settings.supabase_url}/storage/v1/object/sign/{STATEMENT_BUCKET}/{storage_path}",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": settings.supabase_publishable_key,
        },
        json={"expiresIn": expires_in},
    )
    if response.is_error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Statement view link failed"
        )

    signed_path = response.json()["signedURL"]
    return f"{settings.supabase_url}/storage/v1{signed_path}"


def delete_statement(token: str, storage_path: str) -> None:
    response = httpx.delete(
        f"{settings.supabase_url}/storage/v1/object/{STATEMENT_BUCKET}/{storage_path}",
        headers={
            "Authorization": f"Bearer {token}",
            "apikey": settings.supabase_publishable_key,
        },
    )
    if response.is_error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Statement delete failed"
        )
