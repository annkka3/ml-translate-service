from typing import Annotated, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.schemas.auth import TokenOut
from app.infrastructure.db.database import get_db
from app.infrastructure.db.config import get_settings
from app.infrastructure.db.models.user import User
from app.core.security import decode_access_token, create_access_token

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")
oauth2_optional = OAuth2PasswordBearer(tokenUrl="auth/token", auto_error=False)

async def _get_user_by_id(user_id: str, db: AsyncSession) -> Optional[User]:
    res = await db.execute(select(User).where(User.id == user_id))
    return res.scalar_one_or_none()

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id: Optional[str] = payload.get("sub")
        if not user_id:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = await _get_user_by_id(user_id, db)
    if not user:
        raise credentials_exc
    return user

async def get_current_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user

oauth2_optional = OAuth2PasswordBearer(tokenUrl="auth/token", auto_error=False)

async def get_optional_user(
    token: Annotated[Optional[str], Depends(oauth2_optional)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Optional[User]:
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
    except JWTError:
        return None
    return await _get_user_by_id(user_id, db)
