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


@dataclass(frozen=True)
class PlayerProgressSummary:
    player_uuid: str
    display_name: str
    completed_task_count: int
    complete_quest_count: int
    partial_quest_count: int
    known_quest_count: int


@dataclass(frozen=True)
class ChapterProgressSummary:
    player_uuid: str
    display_name: str
    chapter_id: str
    chapter_title: str
    complete_quest_count: int
    partial_quest_count: int
    total_quest_count: int


@dataclass(frozen=True)
class ProgressSummary:
    players: list[PlayerProgressSummary]
    chapters: list[ChapterProgressSummary]


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


def get_progress_summary(settings: DatabaseSettings | None = None) -> ProgressSummary:
    resolved_settings = settings or get_database_settings()

    with psycopg.connect(resolved_settings.dsn, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    p.uuid,
                    p.display_name,
                    COUNT(DISTINCT pct.task_id) AS completed_task_count,
                    COUNT(DISTINCT qcbp.quest_id) FILTER (
                        WHERE qcbp.is_complete
                    ) AS complete_quest_count,
                    COUNT(DISTINCT qcbp.quest_id) FILTER (
                        WHERE NOT qcbp.is_complete
                          AND qcbp.completed_tasks > 0
                    ) AS partial_quest_count,
                    COUNT(DISTINCT qcbp.quest_id) FILTER (
                        WHERE qcbp.completed_tasks > 0
                           OR qcbp.is_complete
                    ) AS known_quest_count
                FROM players p
                    LEFT JOIN player_completed_tasks pct
                        ON pct.player_uuid = p.uuid
                    LEFT JOIN quest_completion_by_player qcbp
                        ON qcbp.player_uuid = p.uuid
                GROUP BY
                    p.uuid,
                    p.display_name
                ORDER BY
                    p.display_name;
                """
            )
            players = [
                PlayerProgressSummary(
                    player_uuid=row[0],
                    display_name=row[1],
                    completed_task_count=row[2],
                    complete_quest_count=row[3],
                    partial_quest_count=row[4],
                    known_quest_count=row[5],
                )
                for row in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT
                    qcbp.player_uuid,
                    qcbp.display_name,
                    qc.id AS chapter_id,
                    qc.title AS chapter_title,
                    COUNT(qcbp.quest_id) FILTER (
                        WHERE qcbp.is_complete
                    ) AS complete_quest_count,
                    COUNT(qcbp.quest_id) FILTER (
                        WHERE NOT qcbp.is_complete
                          AND qcbp.completed_tasks > 0
                    ) AS partial_quest_count,
                    COUNT(qcbp.quest_id) AS total_quest_count
                FROM quest_completion_by_player qcbp
                    JOIN quest_chapters qc
                        ON qc.id = qcbp.chapter_id
                WHERE qcbp.completed_tasks > 0
                   OR qcbp.is_complete
                GROUP BY
                    qcbp.player_uuid,
                    qcbp.display_name,
                    qc.id,
                    qc.title
                ORDER BY
                    qcbp.display_name,
                    complete_quest_count DESC,
                    partial_quest_count DESC,
                    qc.title;
                """
            )
            chapters = [
                ChapterProgressSummary(
                    player_uuid=row[0],
                    display_name=row[1],
                    chapter_id=row[2],
                    chapter_title=row[3],
                    complete_quest_count=row[4],
                    partial_quest_count=row[5],
                    total_quest_count=row[6],
                )
                for row in cursor.fetchall()
            ]

    return ProgressSummary(
        players=players,
        chapters=chapters,
    )