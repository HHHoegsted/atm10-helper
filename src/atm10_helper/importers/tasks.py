from __future__ import annotations

from pathlib import Path

import psycopg

from atm10_helper.config import DatabaseSettings, get_database_settings
from atm10_helper.importers.chapters import (
    CHAPTERS_RELATIVE_PATH,
    parse_chapter_file,
    raise_for_duplicate_chapter_ids,
)
from atm10_helper.importers.models import ParsedQuest, ParsedQuestTask, TaskImportResult
from atm10_helper.importers.quests import (
    parse_quests_for_chapter,
    raise_for_duplicate_quest_ids,
)
from atm10_helper.importers.snbt import (
    extract_item_count_from_item_block,
    extract_item_id_from_item_block,
    extract_top_level_list,
    extract_top_level_object,
    optional_top_level_string_value,
    required_top_level_string_value,
    split_top_level_objects,
)


def import_tasks(
    atm10_path: Path,
    settings: DatabaseSettings | None = None,
) -> TaskImportResult:
    resolved_atm10_path = atm10_path.expanduser().resolve()
    chapters_path = resolved_atm10_path / CHAPTERS_RELATIVE_PATH

    if not resolved_atm10_path.exists():
        raise FileNotFoundError(f"ATM10 path does not exist: {resolved_atm10_path}")

    if not chapters_path.exists():
        raise FileNotFoundError(
            "Could not find FTB Quests chapter directory at "
            f"{chapters_path}. Expected an extracted ATM10 instance folder."
        )

    chapter_files = sorted(chapters_path.glob("*.snbt"))

    if not chapter_files:
        raise FileNotFoundError(f"No .snbt chapter files found in {chapters_path}")

    parsed_chapters = [parse_chapter_file(chapter_file) for chapter_file in chapter_files]
    raise_for_duplicate_chapter_ids(parsed_chapters)

    parsed_quests: list[ParsedQuest] = []

    for chapter_file, chapter in zip(chapter_files, parsed_chapters, strict=True):
        parsed_quests.extend(parse_quests_for_chapter(chapter_file, chapter.id))

    raise_for_duplicate_quest_ids(parsed_quests)

    parsed_tasks: list[ParsedQuestTask] = []

    for quest in parsed_quests:
        parsed_tasks.extend(parse_tasks_for_quest(quest))

    raise_for_duplicate_task_ids(parsed_tasks)

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
                    "ftbquests_tasks",
                    str(resolved_atm10_path),
                    "atm10",
                    "Imported FTB Quests task SNBT blocks.",
                ),
            )
            import_run_id = cursor.fetchone()[0]

            for task in parsed_tasks:
                cursor.execute(
                    """
                    INSERT INTO quest_tasks (
                        id,
                        quest_id,
                        task_type,
                        item_id,
                        item_count,
                        title,
                        raw_snbt,
                        import_run_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        quest_id = EXCLUDED.quest_id,
                        task_type = EXCLUDED.task_type,
                        item_id = EXCLUDED.item_id,
                        item_count = EXCLUDED.item_count,
                        title = EXCLUDED.title,
                        raw_snbt = EXCLUDED.raw_snbt,
                        imported_at = now(),
                        import_run_id = EXCLUDED.import_run_id;
                    """,
                    (
                        task.id,
                        task.quest_id,
                        task.task_type,
                        task.item_id,
                        task.item_count,
                        task.title,
                        task.raw_snbt,
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

    return TaskImportResult(
        source_path=resolved_atm10_path,
        chapter_count=len(parsed_chapters),
        quest_count=len(parsed_quests),
        task_count=len(parsed_tasks),
        import_run_id=str(import_run_id),
    )


def parse_tasks_for_quest(quest: ParsedQuest) -> list[ParsedQuestTask]:
    tasks_list = extract_top_level_list(quest.raw_snbt, "tasks")

    if tasks_list is None:
        return []

    task_blocks = split_top_level_objects(tasks_list)

    return [
        parse_task_block(
            task_block=task_block,
            quest_id=quest.id,
        )
        for task_block in task_blocks
    ]


def parse_task_block(task_block: str, quest_id: str) -> ParsedQuestTask:
    task_id = required_top_level_string_value(task_block, "id", Path(f"quest {quest_id}"))
    task_type = required_top_level_string_value(task_block, "type", Path(f"quest {quest_id}"))
    item_block = extract_top_level_object(task_block, "item")

    return ParsedQuestTask(
        id=task_id,
        quest_id=quest_id,
        task_type=task_type,
        item_id=extract_item_id_from_item_block(item_block),
        item_count=extract_item_count_from_item_block(item_block),
        title=optional_top_level_string_value(task_block, "title"),
        raw_snbt=task_block,
    )


def raise_for_duplicate_task_ids(parsed_tasks: list[ParsedQuestTask]) -> None:
    seen: dict[str, str] = {}

    for task in parsed_tasks:
        if task.id in seen:
            raise ValueError(
                "Duplicate task ID found while importing task blocks: "
                f"{task.id} appears in both quest {seen[task.id]} and quest {task.quest_id}. "
                "Refusing to import because one task would overwrite another."
            )

        seen[task.id] = task.quest_id