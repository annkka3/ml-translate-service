
from typing import Optional
from .settings import Settings

from app.infrastructure.db import config as db_config_module  # type: ignore
from app.infrastructure.db import database as db_database_module  # type: ignore


class Container:
    def __init__(self, settings: Optional[Settings] = None):
        from .settings import get_settings
        self.settings = settings or get_settings()

        # Database config/session providers
        self.db_config = db_config_module
        self.db = db_database_module

        # Bus/publisher
        try:
            from app.infrastructure.bus import publisher as bus_publisher  # type: ignore
            self.bus_publisher = bus_publisher
        except Exception:
            self.bus_publisher = None

container = Container()
