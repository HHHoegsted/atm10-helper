from __future__ import annotations

from pathlib import Path

import psycopg

from atm10_helper.config import DatabaseSettings, get_database_settings
from atm10_helper.importers.chapters import (
    CHAPTERS_RELATIVE_PATH,
    parse_chapter_file,
    raise_for_duplicate_chapter_ids,
)
from atm10_helper.importers.models import ParsedQuest, QuestImportResult
from atm10_helper.importers.snbt import (
    extract_top_level_list,
    optional_top_level_float_value,
    optional_top_level_icon_id,
    optional_top_level_string_value,
    required_top_level_string_value,
    split_top_level_objects,
)


def import_quests(
    atm10_path: Path,
    settings: DatabaseSettings | None = None,
) -> QuestImportResult:
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
                    "ftbquests_quests",
                    str(resolved_atm10_path),
                    "atm10",
                    "Imported FTB Quests quest SNBT blocks.",
                ),
            )
            import_run_id = cursor.fetchone()[0]

            for quest in parsed_quests:
                cursor.execute(
                    """
                    INSERT INTO quests (
                        id,
                        chapter_id,
                        title,
                        subtitle,
                        description,
                        icon_item_id,
                        shape,
                        size,
                        x,
                        y,
                        raw_snbt,
                        import_run_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        chapter_id = EXCLUDED.chapter_id,
                        title = EXCLUDED.title,
                        subtitle = EXCLUDED.subtitle,
                        description = EXCLUDED.description,
                        icon_item_id = EXCLUDED.icon_item_id,
                        shape = EXCLUDED.shape,
                        size = EXCLUDED.size,
                        x = EXCLUDED.x,
                        y = EXCLUDED.y,
                        raw_snbt = EXCLUDED.raw_snbt,
                        imported_at = now(),
                        import_run_id = EXCLUDED.import_run_id;
                    """,
                    (
                        quest.id,
                        quest.chapter_id,
                        quest.title,
                        quest.subtitle,
                        quest.description,
                        quest.icon_item_id,
                        quest.shape,
                        quest.size,
                        quest.x,
                        quest.y,
                        quest.raw_snbt,
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

    return QuestImportResult(
        source_path=resolved_atm10_path,
        chapter_count=len(parsed_chapters),
        quest_count=len(parsed_quests),
        import_run_id=str(import_run_id),
    )


def parse_quests_for_chapter(chapter_file: Path, chapter_id: str) -> list[ParsedQuest]:
    raw_snbt = chapter_file.read_text(encoding="utf-8")
    quests_list = extract_top_level_list(raw_snbt, "quests")

    if quests_list is None:
        return []

    quest_blocks = split_top_level_objects(quests_list)

    return [
        parse_quest_block(
            quest_block=quest_block,
            chapter_id=chapter_id,
            source_file=chapter_file,
        )
        for quest_block in quest_blocks
    ]


def parse_quest_block(
    quest_block: str,
    chapter_id: str,
    source_file: Path,
) -> ParsedQuest:
    quest_id = required_top_level_string_value(quest_block, "id", source_file)

    return ParsedQuest(
        id=quest_id,
        chapter_id=chapter_id,
        title=optional_top_level_string_value(quest_block, "title"),
        subtitle=optional_top_level_string_value(quest_block, "subtitle"),
        description=optional_top_level_string_value(quest_block, "description"),
        icon_item_id=optional_top_level_icon_id(quest_block),
        shape=optional_top_level_string_value(quest_block, "shape"),
        size=optional_top_level_float_value(quest_block, "size"),
        x=optional_top_level_float_value(quest_block, "x"),
        y=optional_top_level_float_value(quest_block, "y"),
        raw_snbt=quest_block,
    )


def raise_for_duplicate_quest_ids(parsed_quests: list[ParsedQuest]) -> None:
    seen: dict[str, str] = {}

    for quest in parsed_quests:
        if quest.id in seen:
            raise ValueError(
                "Duplicate quest ID found while importing quest blocks: "
                f"{quest.id} appears in both chapter {seen[quest.id]} and chapter "
                f"{quest.chapter_id}. Refusing to import because one quest would overwrite another."
            )

        seen[quest.id] = quest.chapter_id