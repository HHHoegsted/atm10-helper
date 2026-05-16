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
class QuestImportResult:
    source_path: Path
    chapter_count: int
    quest_count: int
    import_run_id: str


@dataclass(frozen=True)
class ParsedChapter:
    id: str
    filename: str
    group_id: str | None
    icon_item_id: str | None
    default_quest_shape: str | None
    raw_snbt: str


@dataclass(frozen=True)
class ParsedQuest:
    id: str
    chapter_id: str
    title: str | None
    subtitle: str | None
    description: str | None
    icon_item_id: str | None
    shape: str | None
    size: float | None
    x: float | None
    y: float | None
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

    parsed_chapters = [_parse_chapter_file(chapter_file) for chapter_file in chapter_files]
    _raise_for_duplicate_chapter_ids(parsed_chapters)

    parsed_quests: list[ParsedQuest] = []

    for chapter_file, chapter in zip(chapter_files, parsed_chapters, strict=True):
        parsed_quests.extend(_parse_quests_for_chapter(chapter_file, chapter.id))

    _raise_for_duplicate_quest_ids(parsed_quests)

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


def _parse_quests_for_chapter(chapter_file: Path, chapter_id: str) -> list[ParsedQuest]:
    raw_snbt = chapter_file.read_text(encoding="utf-8")
    quests_list = _extract_top_level_list(raw_snbt, "quests")

    if quests_list is None:
        return []

    quest_blocks = _split_top_level_objects(quests_list)

    return [
        _parse_quest_block(
            quest_block=quest_block,
            chapter_id=chapter_id,
            source_file=chapter_file,
        )
        for quest_block in quest_blocks
    ]


def _parse_quest_block(
    quest_block: str,
    chapter_id: str,
    source_file: Path,
) -> ParsedQuest:
    quest_id = _required_top_level_string_value(quest_block, "id", source_file)

    return ParsedQuest(
        id=quest_id,
        chapter_id=chapter_id,
        title=_optional_top_level_string_value(quest_block, "title"),
        subtitle=_optional_top_level_string_value(quest_block, "subtitle"),
        description=_optional_top_level_string_value(quest_block, "description"),
        icon_item_id=_optional_top_level_icon_id(quest_block),
        shape=_optional_top_level_string_value(quest_block, "shape"),
        size=_optional_top_level_float_value(quest_block, "size"),
        x=_optional_top_level_float_value(quest_block, "x"),
        y=_optional_top_level_float_value(quest_block, "y"),
        raw_snbt=quest_block,
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


def _raise_for_duplicate_quest_ids(parsed_quests: list[ParsedQuest]) -> None:
    seen: dict[str, str] = {}

    for quest in parsed_quests:
        if quest.id in seen:
            raise ValueError(
                "Duplicate quest ID found while importing quest blocks: "
                f"{quest.id} appears in both chapter {seen[quest.id]} and chapter "
                f"{quest.chapter_id}. Refusing to import because one quest would overwrite another."
            )

        seen[quest.id] = quest.chapter_id


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


def _optional_top_level_float_value(raw_snbt: str, key: str) -> float | None:
    depth = 0

    for line in raw_snbt.splitlines():
        stripped_line = line.strip()

        if depth == 1:
            match = re.fullmatch(
                rf"{re.escape(key)}:\s*(-?\d+(?:\.\d+)?)(?:[dDfFlLsSbB])?",
                stripped_line,
            )

            if match is not None:
                return float(match.group(1))

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
    return _extract_top_level_value(
        raw_snbt=raw_snbt,
        key=key,
        opener="{",
    )


def _extract_top_level_list(raw_snbt: str, key: str) -> str | None:
    return _extract_top_level_value(
        raw_snbt=raw_snbt,
        key=key,
        opener="[",
    )


def _extract_top_level_value(raw_snbt: str, key: str, opener: str) -> str | None:
    depth = 0
    position = 0

    for line in raw_snbt.splitlines(keepends=True):
        stripped_line = line.strip()

        if depth == 1 and stripped_line.startswith(f"{key}:"):
            opener_index = line.find(opener)

            if opener_index == -1:
                return None

            value_start = position + opener_index
            value_end = _find_matching_delimiter(raw_snbt, value_start)

            return raw_snbt[value_start : value_end + 1]

        depth = _updated_depth(depth, line)
        position += len(line)

    return None


def _split_top_level_objects(raw_snbt_list: str) -> list[str]:
    stripped_list = raw_snbt_list.strip()

    if not stripped_list.startswith("[") or not stripped_list.endswith("]"):
        raise ValueError("Expected an SNBT list enclosed by '[' and ']'.")

    list_body = stripped_list[1:-1]

    objects: list[str] = []
    depth = 0
    object_start: int | None = None
    in_string = False
    escaped = False

    for index, character in enumerate(list_body):
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
            if depth == 0:
                object_start = index

            depth += 1
            continue

        if character == "}":
            depth -= 1

            if depth == 0 and object_start is not None:
                objects.append(list_body[object_start : index + 1])
                object_start = None

    if depth != 0:
        raise ValueError("Unbalanced braces while splitting SNBT list objects.")

    return objects


def _find_matching_delimiter(raw_snbt: str, opening_index: int) -> int:
    opener = raw_snbt[opening_index]

    if opener == "{":
        closer = "}"
    elif opener == "[":
        closer = "]"
    else:
        raise ValueError(f"Unsupported opening delimiter: {opener}")

    depth = 0
    in_string = False
    escaped = False

    for index in range(opening_index, len(raw_snbt)):
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

        if character == opener:
            depth += 1

        if character == closer:
            depth -= 1

            if depth == 0:
                return index

    raise ValueError(f"Could not find matching closing delimiter for {opener}.")


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