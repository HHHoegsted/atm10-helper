from __future__ import annotations

from pathlib import Path

import psycopg

from atm10_helper.config import DatabaseSettings, get_database_settings
from atm10_helper.importers.models import ChapterImportResult, ParsedChapter
from atm10_helper.importers.snbt import (
    optional_top_level_icon_id,
    optional_top_level_string_value,
    required_top_level_string_value,
    title_from_filename,
)


CHAPTERS_RELATIVE_PATH = Path("config/ftbquests/quests/chapters")


def import_quest_chapters(
    atm10_path: Path,
    settings: DatabaseSettings | None = None,
) -> ChapterImportResult:
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
                    "ftbquests_chapters",
                    str(resolved_atm10_path),
                    "atm10",
                    "Imported FTB Quests chapter SNBT files.",
                ),
            )
            import_run_id = cursor.fetchone()[0]

            for chapter in parsed_chapters:
                cursor.execute(
                    """
                    INSERT INTO quest_chapters (
                        id,
                        filename,
                        group_id,
                        title,
                        subtitle,
                        icon_item_id,
                        order_index,
                        progression_mode,
                        raw_snbt,
                        import_run_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        filename = EXCLUDED.filename,
                        group_id = EXCLUDED.group_id,
                        title = EXCLUDED.title,
                        subtitle = EXCLUDED.subtitle,
                        icon_item_id = EXCLUDED.icon_item_id,
                        order_index = EXCLUDED.order_index,
                        progression_mode = EXCLUDED.progression_mode,
                        raw_snbt = EXCLUDED.raw_snbt,
                        imported_at = now(),
                        import_run_id = EXCLUDED.import_run_id;
                    """,
                    (
                        chapter.id,
                        chapter.filename,
                        chapter.group_id,
                        title_from_filename(chapter.filename),
                        None,
                        chapter.icon_item_id,
                        None,
                        None,
                        chapter.raw_snbt,
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

    return ChapterImportResult(
        source_path=resolved_atm10_path,
        chapter_count=len(parsed_chapters),
        import_run_id=str(import_run_id),
    )


def parse_chapter_file(chapter_file: Path) -> ParsedChapter:
    raw_snbt = chapter_file.read_text(encoding="utf-8")

    chapter_id = required_top_level_string_value(raw_snbt, "id", chapter_file)
    filename = optional_top_level_string_value(raw_snbt, "filename") or chapter_file.stem
    group_id = optional_top_level_string_value(raw_snbt, "group")
    default_quest_shape = optional_top_level_string_value(raw_snbt, "default_quest_shape")
    icon_item_id = optional_top_level_icon_id(raw_snbt)

    return ParsedChapter(
        id=chapter_id,
        filename=filename,
        group_id=group_id,
        icon_item_id=icon_item_id,
        default_quest_shape=default_quest_shape,
        raw_snbt=raw_snbt,
    )


def raise_for_duplicate_chapter_ids(parsed_chapters: list[ParsedChapter]) -> None:
    seen: dict[str, str] = {}

    for chapter in parsed_chapters:
        if chapter.id in seen:
            raise ValueError(
                "Duplicate chapter ID found while importing chapter files: "
                f"{chapter.id} appears in both {seen[chapter.id]} and {chapter.filename}. "
                "Refusing to import because one chapter would overwrite another."
            )

        seen[chapter.id] = chapter.filename