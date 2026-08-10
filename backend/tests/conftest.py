from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.core import security

TEST_USER_ID = "11111111-1111-4111-8111-111111111111"


@pytest.fixture(autouse=True)
def patch_jwks(monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    fake_jwks_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=public_key)
    )
    monkeypatch.setattr(security, "_jwks_client", lambda: fake_jwks_client)

    return private_key


@pytest.fixture
def make_token(patch_jwks):
    def _make_token(sub: str = TEST_USER_ID, **extra_claims) -> str:
        payload = {"sub": sub, "email": "test@example.com", "aud": "authenticated", **extra_claims}
        return jwt.encode(payload, patch_jwks, algorithm="ES256")

    return _make_token
