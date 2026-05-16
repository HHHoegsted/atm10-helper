from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    database: str
    user: str
    password: str

    @property
    def dsn(self) -> str:
        return (
            f"host={self.host} "
            f"port={self.port} "
            f"dbname={self.database} "
            f"user={self.user} "
            f"password={self.password}"
        )


def get_database_settings() -> DatabaseSettings:
    load_dotenv()

    return DatabaseSettings(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5434")),
        database=os.getenv("POSTGRES_DB", "atm10_helper"),
        user=os.getenv("POSTGRES_USER", "atm10_helper"),
        password=os.getenv("POSTGRES_PASSWORD", "atm10_helper_dev_password"),
    )