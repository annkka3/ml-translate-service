## app/api/routers/home.py
from typing import Dict
from fastapi import APIRouter

router = APIRouter(tags=["Home"])

@router.get("/", response_model=Dict[str, str])
async def index() -> Dict[str, str]:
    return {"message": "Welcome to translation service..."}

@router.get("/health", response_model=Dict[str, str])
async def health() -> Dict[str, str]:
    return {"status": "healthy"}