from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import psycopg

from atm10_helper.config import DatabaseSettings, get_database_settings


CHAPTERS_RELATIVE_PATH = Path("config/ftbquests/quests/chapters")


@dataclass(frozen=True)
class ChapterImportResult:
    source_path: Path
    chapter_count: int
    import_run_id: str


@dataclass(frozen=True)
class ParsedChapter:
    id: str
    filename: str
    group_id: str | None
    icon_item_id: str | None
    default_quest_shape: str | None
    raw_snbt: str


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

    parsed_chapters = [_parse_chapter_file(chapter_file) for chapter_file in chapter_files]
    _raise_for_duplicate_chapter_ids(parsed_chapters)

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
                        _title_from_filename(chapter.filename),
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


def _parse_chapter_file(chapter_file: Path) -> ParsedChapter:
    raw_snbt = chapter_file.read_text(encoding="utf-8")

    chapter_id = _required_top_level_string_value(raw_snbt, "id", chapter_file)
    filename = _optional_top_level_string_value(raw_snbt, "filename") or chapter_file.stem
    group_id = _optional_top_level_string_value(raw_snbt, "group")
    default_quest_shape = _optional_top_level_string_value(raw_snbt, "default_quest_shape")
    icon_item_id = _optional_top_level_icon_id(raw_snbt)

    return ParsedChapter(
        id=chapter_id,
        filename=filename,
        group_id=group_id,
        icon_item_id=icon_item_id,
        default_quest_shape=default_quest_shape,
        raw_snbt=raw_snbt,
    )


def _raise_for_duplicate_chapter_ids(parsed_chapters: list[ParsedChapter]) -> None:
    seen: dict[str, str] = {}

    for chapter in parsed_chapters:
        if chapter.id in seen:
            raise ValueError(
                "Duplicate chapter ID found while importing chapter files: "
                f"{chapter.id} appears in both {seen[chapter.id]} and {chapter.filename}. "
                "Refusing to import because one chapter would overwrite another."
            )

        seen[chapter.id] = chapter.filename


def _required_top_level_string_value(raw_snbt: str, key: str, source_file: Path) -> str:
    value = _optional_top_level_string_value(raw_snbt, key)

    if value is None:
        raise ValueError(f"Could not find required top-level key '{key}' in {source_file}")

    return value


def _optional_top_level_string_value(raw_snbt: str, key: str) -> str | None:
    depth = 0

    for line in raw_snbt.splitlines():
        stripped_line = line.strip()

        if depth == 1:
            match = re.fullmatch(rf'{re.escape(key)}:\s*"([^"]*)"', stripped_line)

            if match is not None:
                return match.group(1)

        depth = _updated_depth(depth, line)

    return None


def _optional_top_level_icon_id(raw_snbt: str) -> str | None:
    icon_block = _extract_top_level_object(raw_snbt, "icon")

    if icon_block is None:
        return None

    custom_icon_match = re.search(r'"ftbquests:icon":\s*"([^"]+)"', icon_block)

    if custom_icon_match is not None:
        return custom_icon_match.group(1)

    id_match = re.search(r'^\s*id:\s*"([^"]+)"', icon_block, re.MULTILINE)

    if id_match is None:
        return None

    return id_match.group(1)


def _extract_top_level_object(raw_snbt: str, key: str) -> str | None:
    depth = 0
    position = 0

    for line in raw_snbt.splitlines(keepends=True):
        stripped_line = line.strip()

        if depth == 1 and stripped_line.startswith(f"{key}:"):
            opening_brace_index = line.find("{")

            if opening_brace_index == -1:
                return None

            object_start = position + opening_brace_index
            object_end = _find_matching_brace(raw_snbt, object_start)

            return raw_snbt[object_start : object_end + 1]

        depth = _updated_depth(depth, line)
        position += len(line)

    return None


def _find_matching_brace(raw_snbt: str, opening_brace_index: int) -> int:
    depth = 0
    in_string = False
    escaped = False

    for index in range(opening_brace_index, len(raw_snbt)):
        character = raw_snbt[index]

        if escaped:
            escaped = False
            continue

        if character == "\\":
            escaped = True
            continue

        if character == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if character == "{":
            depth += 1

        if character == "}":
            depth -= 1

            if depth == 0:
                return index

    raise ValueError("Could not find matching closing brace in SNBT object.")


def _updated_depth(current_depth: int, line: str) -> int:
    depth = current_depth
    in_string = False
    escaped = False

    for character in line:
        if escaped:
            escaped = False
            continue

        if character == "\\":
            escaped = True
            continue

        if character == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if character in "{[":
            depth += 1

        if character in "}]":
            depth -= 1

    return depth


def _title_from_filename(filename: str) -> str:
    return filename.replace("_2r_", " ").replace("_6", "").replace("_", " ").title()