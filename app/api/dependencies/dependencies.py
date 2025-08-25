
from fastapi import Depends
from app.core.container import container

def get_db():
    try:
        from app.infrastructure.db.database import get_db as original_get_db  # type: ignore
        return Depends(original_get_db)
    except Exception:
        def _noop():
            return None
        return Depends(_noop)

def get_current_user():
    from app.api.dependencies.auth import get_current_user as _get_current_user  # type: ignore
    return Depends(_get_current_user)
