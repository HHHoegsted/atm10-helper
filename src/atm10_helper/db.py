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
class Player:
    player_uuid: str
    display_name: str


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


@dataclass(frozen=True)
class MissingTask:
    player_uuid: str
    quest_id: str
    task_id: str
    task_type: str
    title: str | None
    item_id: str | None
    item_count: int | None


@dataclass(frozen=True)
class PartialQuest:
    player_uuid: str
    display_name: str
    chapter_id: str
    chapter_title: str
    quest_id: str
    quest_title: str | None
    completed_tasks: int
    total_tasks: int
    missing_tasks: int
    missing_task_details: list[MissingTask]


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


def get_players(settings: DatabaseSettings | None = None) -> list[Player]:
    resolved_settings = settings or get_database_settings()

    with psycopg.connect(resolved_settings.dsn, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    uuid,
                    display_name
                FROM players
                ORDER BY display_name;
                """
            )

            return [
                Player(
                    player_uuid=row[0],
                    display_name=row[1],
                )
                for row in cursor.fetchall()
            ]


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


def get_partial_quests(
    player_filter: str | None = None,
    settings: DatabaseSettings | None = None,
) -> list[PartialQuest]:
    resolved_settings = settings or get_database_settings()

    player_filter_clause = ""
    query_parameters: dict[str, str | list[str]] = {}

    if player_filter is not None:
        player_filter_clause = "AND qcbp.display_name ILIKE %(player_filter_pattern)s"
        query_parameters["player_filter_pattern"] = f"%{player_filter}%"

    with psycopg.connect(resolved_settings.dsn, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    qcbp.player_uuid,
                    qcbp.display_name,
                    qc.id AS chapter_id,
                    qc.title AS chapter_title,
                    qcbp.quest_id,
                    qcbp.quest_title,
                    qcbp.completed_tasks,
                    qcbp.total_tasks,
                    qcbp.total_tasks - qcbp.completed_tasks AS missing_tasks
                FROM quest_completion_by_player qcbp
                    JOIN quest_chapters qc
                        ON qc.id = qcbp.chapter_id
                WHERE qcbp.completed_tasks > 0
                  AND NOT qcbp.is_complete
                  {player_filter_clause}
                ORDER BY
                    qcbp.display_name,
                    qcbp.completed_tasks DESC,
                    missing_tasks ASC,
                    qc.title,
                    qcbp.quest_title;
                """,
                query_parameters,
            )
            partial_quests = [
                PartialQuest(
                    player_uuid=row[0],
                    display_name=row[1],
                    chapter_id=row[2],
                    chapter_title=row[3],
                    quest_id=row[4],
                    quest_title=row[5],
                    completed_tasks=row[6],
                    total_tasks=row[7],
                    missing_tasks=row[8],
                    missing_task_details=[],
                )
                for row in cursor.fetchall()
            ]

            if not partial_quests:
                return []

            quest_keys = [
                (quest.player_uuid, quest.quest_id)
                for quest in partial_quests
            ]

            cursor.execute(
                """
                SELECT
                    missing.player_uuid,
                    missing.quest_id,
                    missing.task_id,
                    missing.task_type,
                    missing.title,
                    missing.item_id,
                    missing.item_count
                FROM (
                    SELECT
                        selected.player_uuid,
                        qt.quest_id,
                        qt.id AS task_id,
                        qt.task_type,
                        qt.title,
                        qt.item_id,
                        qt.item_count
                    FROM (
                        SELECT
                            UNNEST(%(player_uuids)s::text[]) AS player_uuid,
                            UNNEST(%(quest_ids)s::text[]) AS quest_id
                    ) selected
                        JOIN quest_tasks qt
                            ON qt.quest_id = selected.quest_id
                        LEFT JOIN player_completed_tasks pct
                            ON pct.player_uuid = selected.player_uuid
                           AND pct.task_id = qt.id
                    WHERE pct.task_id IS NULL
                ) missing
                ORDER BY
                    missing.player_uuid,
                    missing.quest_id,
                    CASE missing.task_type
                        WHEN 'item' THEN 0
                        ELSE 1
                    END,
                    missing.task_type,
                    missing.item_id,
                    missing.title,
                    missing.task_id;
                """,
                {
                    "player_uuids": [player_uuid for player_uuid, _ in quest_keys],
                    "quest_ids": [quest_id for _, quest_id in quest_keys],
                },
            )

            missing_tasks_by_quest_key: dict[tuple[str, str], list[MissingTask]] = {}

            for row in cursor.fetchall():
                missing_task = MissingTask(
                    player_uuid=row[0],
                    quest_id=row[1],
                    task_id=row[2],
                    task_type=row[3],
                    title=row[4],
                    item_id=row[5],
                    item_count=row[6],
                )
                missing_tasks_by_quest_key.setdefault(
                    (missing_task.player_uuid, missing_task.quest_id),
                    [],
                ).append(missing_task)

    return [
        PartialQuest(
            player_uuid=quest.player_uuid,
            display_name=quest.display_name,
            chapter_id=quest.chapter_id,
            chapter_title=quest.chapter_title,
            quest_id=quest.quest_id,
            quest_title=quest.quest_title,
            completed_tasks=quest.completed_tasks,
            total_tasks=quest.total_tasks,
            missing_tasks=quest.missing_tasks,
            missing_task_details=missing_tasks_by_quest_key.get(
                (quest.player_uuid, quest.quest_id),
                [],
            ),
        )
        for quest in partial_quests
    ]