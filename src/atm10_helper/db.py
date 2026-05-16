from __future__ import annotations

from dataclasses import dataclass

import psycopg

from atm10_helper.config import DatabaseSettings, get_database_settings


@dataclass(frozen=True)
class DatabaseCheck:
    database_name: str
    database_user: str
    postgres_version: str
    table_count: int
    view_count: int


def check_database(settings: DatabaseSettings | None = None) -> DatabaseCheck:
    resolved_settings = settings or get_database_settings()

    with psycopg.connect(resolved_settings.dsn, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user, version();")
            database_name, database_user, postgres_version = cursor.fetchone()

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE';
                """
            )
            table_count = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.views
                WHERE table_schema = 'public';
                """
            )
            view_count = cursor.fetchone()[0]

    return DatabaseCheck(
        database_name=database_name,
        database_user=database_user,
        postgres_version=postgres_version,
        table_count=table_count,
        view_count=view_count,
    )