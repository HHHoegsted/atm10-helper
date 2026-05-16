from __future__ import annotations

import re
from pathlib import Path

import psycopg

from atm10_helper.config import DatabaseSettings, get_database_settings
from atm10_helper.importers.models import ParsedPlayerProgress, ProgressImportResult
from atm10_helper.importers.snbt import (
    extract_top_level_object,
    optional_top_level_string_value,
    required_top_level_string_value,
)


PROGRESS_RELATIVE_PATH = Path("ftbquests")


def import_progress(
    atm10_path: Path,
    settings: DatabaseSettings | None = None,
) -> ProgressImportResult:
    resolved_atm10_path = atm10_path.expanduser().resolve()
    progress_path = resolved_atm10_path / PROGRESS_RELATIVE_PATH

    if not resolved_atm10_path.exists():
        raise FileNotFoundError(f"ATM10 path does not exist: {resolved_atm10_path}")

    if not progress_path.exists():
        raise FileNotFoundError(
            "Could not find FTB Quests progress directory at "
            f"{progress_path}. Expected an ATM10 instance folder with player progress."
        )

    progress_files = sorted(progress_path.glob("*.snbt"))

    if not progress_files:
        raise FileNotFoundError(f"No .snbt player progress files found in {progress_path}")

    parsed_players = [
        parse_player_progress_file(progress_file)
        for progress_file in progress_files
    ]

    raise_for_duplicate_player_uuids(parsed_players)

    task_progress_count = sum(
        len(player.task_progress)
        for player in parsed_players
    )

    resolved_settings = settings or get_database_settings()

    with psycopg.connect(resolved_settings.dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO import_runs (source_label, source_path, modpack_slug, notes)
                VALUES (%s, %s, %s, %s)
                RETURNING id;
                """,
                (
                    "ftbquests_player_progress",
                    str(resolved_atm10_path),
                    "atm10",
                    "Imported FTB Quests player task progress SNBT files.",
                ),
            )
            import_run_id = cursor.fetchone()[0]

            for player in parsed_players:
                cursor.execute(
                    """
                    INSERT INTO players (
                        uuid,
                        display_name,
                        raw_snbt,
                        import_run_id
                    )
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (uuid)
                    DO UPDATE SET
                        display_name = EXCLUDED.display_name,
                        raw_snbt = EXCLUDED.raw_snbt,
                        imported_at = now(),
                        import_run_id = EXCLUDED.import_run_id;
                    """,
                    (
                        player.uuid,
                        player.display_name,
                        player.raw_snbt,
                        import_run_id,
                    ),
                )

                for task_id, progress_value in player.task_progress.items():
                    cursor.execute(
                        """
                        INSERT INTO player_task_progress (
                            player_uuid,
                            task_id,
                            progress_value,
                            import_run_id
                        )
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (player_uuid, task_id)
                        DO UPDATE SET
                            progress_value = EXCLUDED.progress_value,
                            imported_at = now(),
                            import_run_id = EXCLUDED.import_run_id;
                        """,
                        (
                            player.uuid,
                            task_id,
                            progress_value,
                            import_run_id,
                        ),
                    )

            cursor.execute(
                """
                UPDATE import_runs
                SET finished_at = now()
                WHERE id = %s;
                """,
                (import_run_id,),
            )

        connection.commit()

    return ProgressImportResult(
        source_path=resolved_atm10_path,
        player_count=len(parsed_players),
        task_progress_count=task_progress_count,
        import_run_id=str(import_run_id),
    )


def parse_player_progress_file(progress_file: Path) -> ParsedPlayerProgress:
    raw_snbt = progress_file.read_text(encoding="utf-8")

    player_uuid = required_top_level_string_value(raw_snbt, "uuid", progress_file)
    display_name = (
        optional_top_level_string_value(raw_snbt, "name")
        or progress_file.stem
    )
    task_progress_block = extract_top_level_object(raw_snbt, "task_progress")

    return ParsedPlayerProgress(
        uuid=player_uuid,
        display_name=display_name,
        task_progress=parse_task_progress_block(task_progress_block),
        raw_snbt=raw_snbt,
    )


def parse_task_progress_block(task_progress_block: str | None) -> dict[str, int]:
    if task_progress_block is None:
        return {}

    task_progress: dict[str, int] = {}

    for line in task_progress_block.splitlines():
        stripped_line = line.strip()
        match = re.fullmatch(
            r"([A-Fa-f0-9]+):\s*(-?\d+)(?:[dDfFlLsSbB])?",
            stripped_line,
        )

        if match is None:
            continue

        task_id = match.group(1)
        progress_value = int(match.group(2))
        task_progress[task_id] = progress_value

    return task_progress


def raise_for_duplicate_player_uuids(parsed_players: list[ParsedPlayerProgress]) -> None:
    seen: dict[str, str] = {}

    for player in parsed_players:
        if player.uuid in seen:
            raise ValueError(
                "Duplicate player UUID found while importing player progress files: "
                f"{player.uuid} appears for both {seen[player.uuid]} and "
                f"{player.display_name}. Refusing to import because one player would "
                "overwrite another."
            )

        seen[player.uuid] = player.display_name