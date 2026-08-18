import uuid

import pytest
from fastapi import HTTPException

from app.services.storage import upload_avatar, upload_statement


def test_upload_avatar_rejects_unsupported_content_type() -> None:
    with pytest.raises(HTTPException) as exc_info:
        upload_avatar(user_id="u1", token="t", content_type="image/gif", data=b"x")

    assert exc_info.value.status_code == 415


def test_upload_avatar_rejects_oversized_file() -> None:
    with pytest.raises(HTTPException) as exc_info:
        upload_avatar(
            user_id="u1",
            token="t",
            content_type="image/png",
            data=b"x" * (5 * 1024 * 1024 + 1),
        )

    assert exc_info.value.status_code == 413


def test_upload_statement_rejects_unsupported_content_type() -> None:
    with pytest.raises(HTTPException) as exc_info:
        upload_statement(
            user_id="u1",
            statement_id=uuid.uuid4(),
            token="t",
            content_type="image/png",
            data=b"x",
        )

    assert exc_info.value.status_code == 415


def test_upload_statement_rejects_oversized_file() -> None:
    with pytest.raises(HTTPException) as exc_info:
        upload_statement(
            user_id="u1",
            statement_id=uuid.uuid4(),
            token="t",
            content_type="application/pdf",
            data=b"x" * (20 * 1024 * 1024 + 1),
        )

    assert exc_info.value.status_code == 413
