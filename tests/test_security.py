import pytest
from fastapi import HTTPException
from datetime import timedelta

from app.core.security import create_access_token, decode_access_token

def test_token_roundtrip():
    token = create_access_token({"sub": "user-123"})
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"
    assert "exp" in payload and "iat" in payload

def test_token_expired_raises():
    token = create_access_token({"sub": "user-123"}, expires_delta=timedelta(seconds=-1))
    with pytest.raises(HTTPException) as ei:
        decode_access_token(token)
    err = ei.value
    assert err.status_code == 401
    assert "expired" in err.detail.lower()

def test_overrides_work():
    token = create_access_token({"sub": "abc"}, minutes=1, algorithm="HS256")
    payload = decode_access_token(token, algorithms=["HS256"])
    assert payload["sub"] == "abc"
