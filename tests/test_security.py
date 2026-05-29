import pytest

from app.core.security import create_access_token, decode_token, hash_password, verify_password


def test_hash_password_creates_bcrypt_hash():
    h = hash_password("secret123")
    assert h.startswith("$2b$")
    assert h != "secret123"


def test_verify_password_correct():
    h = hash_password("senha_certa")
    assert verify_password("senha_certa", h) is True


def test_verify_password_wrong():
    h = hash_password("senha_certa")
    assert verify_password("senha_errada", h) is False


def test_create_and_decode_access_token():
    import uuid

    user_id = str(uuid.uuid4())
    token = create_access_token(subject=user_id, role="gestor")
    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["role"] == "gestor"


def test_decode_invalid_token_raises():
    import jwt

    with pytest.raises(jwt.PyJWTError):
        decode_token("token.invalido.aqui")
