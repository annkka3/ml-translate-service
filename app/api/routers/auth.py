# app/api/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from fastapi.security import OAuth2PasswordRequestForm
from app.infrastructure.db.database import get_db
from app.infrastructure.db.config import get_settings
from app.core.security import create_access_token
from app.api.dependencies.auth import get_current_user
from app.infrastructure.db.models.user import User
from app.infrastructure.db.models.wallet import Wallet
from app.domain.schemas.auth import TokenOut, ProfileOut, SignResponse, UserAuth

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/register", response_model=SignResponse, status_code=status.HTTP_201_CREATED)
async def register(data: UserAuth, db: AsyncSession = Depends(get_db)) -> SignResponse:
    """
    Регистрация пользователя (идемпотентная):
      - нормализует email
      - атомарно создаёт пользователя и пустой кошелёк
      - 409, если email уже используется
    """
    email = (data.email or "").strip().lower()
    if not email or not data.password:
        raise HTTPException(status_code=422, detail="email and password are required")

    try:
        async with db.begin():
            # предикативная проверка (ускоряет happy-path) + защитимся от гонок try/except ниже
            res = await db.execute(select(User).where(User.email == email))
            if res.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="User with this email already exists")

            # создание пользователя
            user = User(email=email)
            if hasattr(user, "set_password"):
                user.set_password(data.password)
            elif hasattr(User, "create_instance"):
                # на случай кастомной фабрики в вашей модели
                user = User.create_instance(email=email, password=data.password, initial_balance=0)  # type: ignore[attr-defined]
            else:
                raise HTTPException(status_code=500, detail="User model missing set_password()")

            db.add(user)
            await db.flush()  # чтобы получить user.id

            # создаём связанный кошелёк
            wallet = Wallet(user_id=user.id, balance=0)
            db.add(wallet)

        # вне транзакции — безопасно обновить объект
        # (альтернатива: вернуть из локальной переменной, но refresh точно синхронизирует состояние)
        await db.refresh(user)
        return SignResponse(id=str(user.id), email=user.email, message="Registered")

    except IntegrityError:
        # защита от условий гонки при одновременной регистрации одного email
        raise HTTPException(status_code=409, detail="User with this email already exists")


@router.post("/login", response_model=TokenOut)
async def login(data: UserAuth, db: AsyncSession = Depends(get_db)) -> TokenOut:
    """
    Логин по email + password. Возвращает JWT access token.
    На ошибки даёт 401 и скрывает, существует ли пользователь.
    """
    email = (data.email or "").strip().lower()
    if not email or not data.password:
        raise HTTPException(status_code=422, detail="email and password are required")

    res = await db.execute(select(User).where(User.email == email))
    user = res.scalar_one_or_none()

    if not user or not hasattr(user, "check_password") or not user.check_password(data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        data={"sub": str(user.id)},
        secret_key=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
        minutes=int(settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    # pydantic v1/v2 совместимость по TokenOut
    try:
        return TokenOut(access_token=token, token_type="bearer")
    except TypeError:
        return TokenOut(access_token=token)


@router.get("/me", response_model=ProfileOut)
async def me(current_user: User = Depends(get_current_user)) -> ProfileOut:
    """
    Текущий профиль.
    """
    return ProfileOut(id=str(current_user.id), email=current_user.email)

@router.post("/token", response_model=TokenOut)
async def issue_token(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)) -> TokenOut:
    """
    OAuth2 Password flow для Swagger/UI: принимает form-urlencoded (username, password),
    где username — это email. Возвращает bearer токен.
    """
    email = (form.username or "").strip().lower()
    res = await db.execute(select(User).where(User.email == email))
    user = res.scalar_one_or_none()

    if not user or not hasattr(user, "check_password") or not user.check_password(form.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(
        data={"sub": str(user.id)},
        secret_key=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
        minutes=int(settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    # Swagger ждёт {access_token, token_type}
    return TokenOut(access_token=token, token_type="bearer")


@router.post("/token", response_model=TokenOut)
async def issue_token(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    email = (form.username or "").strip().lower()
    res = await db.execute(select(User).where(User.email == email))
    user = res.scalar_one_or_none()
    if not user or not user.check_password(form.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(
        data={"sub": str(user.id)},
        secret_key=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
        minutes=int(settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return TokenOut(access_token=token, token_type="bearer")