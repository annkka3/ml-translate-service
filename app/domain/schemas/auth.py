
from pydantic import BaseModel, EmailStr

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class ProfileOut(BaseModel):
    id: str
    email: EmailStr

class SignResponse(BaseModel):
    id: str
    email: EmailStr

class RegisterIn(BaseModel):
    email: EmailStr
    password: str


class UserAuth(BaseModel):
    email: EmailStr
    password: str
