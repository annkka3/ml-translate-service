# app/domain/schemas/auth.py
from __future__ import annotations
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProfileOut(BaseModel):
    id: str
    email: EmailStr

    # позволяет возвращать ORM-объекты напрямую
    model_config = ConfigDict(from_attributes=True)


class SignResponse(BaseModel):
    id: str
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    """
    Схема для регистрации через REST (если нужна отдельно от UserAuth).
    """
    email: EmailStr
    password: str = Field(..., min_length=1)


class UserAuth(BaseModel):
    """
    Схема учётных данных для /auth/login и /auth/register.
    """
    email: EmailStr
    password: str = Field(..., min_length=1)
